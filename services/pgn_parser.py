"""
Парсер PGN файлов для извлечения шахматных партий
"""
import re
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from io import StringIO

import chess.pgn

from core.models.game import Game
from core.exceptions.custom_exceptions import PGNParseError, ValidationError


class PGNParser:
    """
    Парсер PGN файлов с Lichess
    
    Извлекает из PGN:
    - Метаданные игры (дата, контроль времени, игроки, рейтинги)
    - Результат и точность
    - Дебют и ходы
    - Ссылку на игру
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Регулярные выражения для извлечения данных
        self.patterns = {
            'game_id': r'\[LichessGameID "([^"]+)"\]',
            'site': r'\[Site "([^"]+)"\]',
            'date': r'\[Date "([^"]+)"\]',
            'white': r'\[White "([^"]+)"\]',
            'black': r'\[Black "([^"]+)"\]',
            'result': r'\[Result "([^"]+)"\]',
            'time_control': r'\[TimeControl "([^"]+)"\]',
            'eco': r'\[ECO "([^"]+)"\]',
            'opening': r'\[Opening "([^"]+)"\]',
            'white_elo': r'\[WhiteElo "([^"]+)"\]',
            'black_elo': r'\[BlackElo "([^"]+)"\]',
            'white_rating_diff': r'\[WhiteRatingDiff "([^"]+)"\]',
            'black_rating_diff': r'\[BlackRatingDiff "([^"]+)"\]',
            'accuracy_white': r'\[WhiteAccuracy "([^"]+)"\]',
            'accuracy_black': r'\[BlackAccuracy "([^"]+)"\]',
            'game_url': r'\[Site "([^"]+)"\]',
        }
    
    def parse_file(self, file_path: str, player_name: str) -> List[Game]:
        """
        Парсит PGN файл и возвращает список игр
        
        Args:
            file_path: Путь к PGN файлу
            player_name: Имя игрока (для определения его цвета и результата)
            
        Returns:
            List[Game]: Список игр
            
        Raises:
            PGNParseError: Если файл не найден или поврежден
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return self.parse_content(content, player_name)
            
        except FileNotFoundError as e:
            raise PGNParseError(f"Файл не найден: {file_path}")
        except Exception as e:
            raise PGNParseError(f"Ошибка чтения файла: {e}")
    
    def parse_content(self, content: str, player_name: str) -> List[Game]:
        """
        Парсит PGN контент и возвращает список игр
        
        Args:
            content: Строка с PGN данными
            player_name: Имя игрока
            
        Returns:
            List[Game]: Список игр
        """
        games = []
        pgn_stream = StringIO(content)
        
        # Подсчет игр для прогресса
        game_count = 0
        
        while True:
            try:
                game_node = chess.pgn.read_game(pgn_stream)
                if game_node is None:
                    break
                
                game_count += 1
                
                try:
                    game = self.parse_single_game(game_node, player_name)
                    if game:
                        games.append(game)
                        
                    if game_count % 50 == 0:
                        self.logger.info(f"Обработано {game_count} игр...")
                        
                except Exception as e:
                    self.logger.warning(f"Ошибка парсинга игры #{game_count}: {e}")
                    continue
                    
            except Exception as e:
                self.logger.error(f"Ошибка в потоке PGN на игре #{game_count}: {e}")
                break
        
        self.logger.info(f"Всего обработано {game_count} игр, успешно: {len(games)}")
        return games
        
    def parse_single_game(self, game_node: chess.pgn.Game, player_name: str) -> Optional[Game]:
        """
        Парсит одну игру из PGN узла
        """
        headers = game_node.headers
        
        # Извлекаем основные данные
        game_id = self._get_header(headers, 'GameId')
        if not game_id:
            game_id = self._get_header(headers, 'LichessGameID')
        
        if not game_id:
            site = self._get_header(headers, 'Site')
            if site:
                match = re.search(r'lichess\.org/([a-zA-Z0-9]+)', site)
                if match:
                    game_id = match.group(1)
        
        # Дата
        date_str = self._get_header(headers, 'Date')
        game_date = self._parse_date(date_str)
        
        # Определяем цвет игрока
        white = self._get_header(headers, 'White')
        black = self._get_header(headers, 'Black')
        
        if not white or not black:
            self.logger.warning("Не удалось определить игроков")
            return None
        
        if player_name.lower() in white.lower():
            player_color = 'white'
            opponent_name = black
            my_rating = self._get_rating(headers, 'WhiteElo')
            opponent_rating = self._get_rating(headers, 'BlackElo')
            accuracy = self._get_accuracy(headers, 'WhiteAccuracy')
        elif player_name.lower() in black.lower():
            player_color = 'black'
            opponent_name = white
            my_rating = self._get_rating(headers, 'BlackElo')
            opponent_rating = self._get_rating(headers, 'WhiteElo')
            accuracy = self._get_accuracy(headers, 'BlackAccuracy')
        else:
            # Игрок не найден - пропускаем игру
            self.logger.debug(f"Игрок {player_name} не найден в игре: {white} vs {black}")
            return None
        
        # Контроль времени
        time_control = self._get_header(headers, 'TimeControl', 'unknown')
        
        # Результат
        result_str = self._get_header(headers, 'Result', '*')
        result = self._determine_result(result_str, player_color)
        
        # Количество ходов
        move_count = self._count_moves(game_node)
        
        # Дебют
        opening_name = self._get_header(headers, 'Opening')
        if not opening_name:
            opening_name = self._get_header(headers, 'ECO')
        
        # Ссылка на игру
        site = self._get_header(headers, 'Site')
        game_url = site if site else None
        
        # PGN нотация
        pgn_moves = self._get_pgn_moves(game_node)
        
        # Анализ (пока пустой)
        game_analysis = None
        
        # Создаем объект Game
        try:
            game = Game(
                game_id=game_id or f"unknown_{game_date.strftime('%Y%m%d')}",
                game_date=game_date,  # ← Только это поле
                time_control=time_control,
                player_color=player_color,
                result=result,
                move_count=move_count,
                opponent_name=opponent_name,
                my_rating=my_rating,
                opponent_rating=opponent_rating,
                accuracy=accuracy,
                opening_name=opening_name,
                opponent_games_count=None,
                game_analysis=game_analysis,
                game_url=game_url,
                pgn_moves=pgn_moves,
                import_source='file'
            )
            
            return game
                
        except ValidationError as e:
            self.logger.warning(f"Ошибка валидации игры {game_id}: {e}")
            return None
        except Exception as e:
            self.logger.warning(f"Ошибка создания игры {game_id}: {e}")
            return None
    
    def _get_header(self, headers: Dict, key: str, default: str = None) -> str:
        """Безопасное получение заголовка"""
        value = headers.get(key, default)
        if value is None:
            return default
        return str(value).strip()
    
    def _parse_date(self, date_str: str) -> datetime:
        """Парсит дату из строки"""
        if not date_str or date_str == '?':
            # Если дата не указана, используем сегодня
            return datetime.now()
        
        try:
            # Формат: YYYY.MM.DD или YYYY-MM-DD
            date_str = date_str.replace('-', '.').replace('/', '.')
            return datetime.strptime(date_str, '%Y.%m.%d')
        except ValueError:
            try:
                # Попробуем другой формат
                return datetime.strptime(date_str, '%Y.%m.%d')
            except ValueError:
                self.logger.warning(f"Не удалось распарсить дату: {date_str}")
                return datetime.now()
    
    def _get_rating(self, headers: Dict, key: str) -> int:
        """Извлекает рейтинг из заголовка"""
        value = self._get_header(headers, key, '0')
        try:
            return int(value) if value.isdigit() else 0
        except (ValueError, AttributeError):
            return 0
    
    def _get_accuracy(self, headers: Dict, key: str) -> Optional[float]:
        """Извлекает точность игры"""
        value = self._get_header(headers, key)
        if not value:
            return None
        try:
            accuracy = float(value)
            return accuracy
        except (ValueError, TypeError):
            return None
    
    def _determine_result(self, result_str: str, player_color: str) -> str:
        """
        Определяет результат для игрока
        
        Args:
            result_str: Строка результата из PGN (например, "1-0", "0-1", "1/2-1/2")
            player_color: Цвет фигур игрока
            
        Returns:
            str: "Win", "Loss" или "Draw"
        """
        if result_str == '1-0':
            return 'Win' if player_color == 'white' else 'Loss'
        elif result_str == '0-1':
            return 'Win' if player_color == 'black' else 'Loss'
        elif result_str in ['1/2-1/2', '½-½']:
            return 'Draw'
        else:
            # Неизвестный результат
            self.logger.warning(f"Неизвестный результат: {result_str}")
            return 'Draw'
    
    def _count_moves(self, game_node: chess.pgn.Game) -> int:
        """Подсчитывает количество ходов в игре"""
        try:
            # Получаем основную вариацию
            main_line = list(game_node.mainline_moves())
            return len(main_line)
        except Exception:
            # Если не удалось подсчитать ходы, используем длину PGN
            try:
                pgn_str = str(game_node)
                # Приблизительный подсчет ходов по количеству чисел в PGN
                import re
                moves = re.findall(r'\d+\.', pgn_str)
                return len(moves)
            except Exception:
                return 0
    
    def _get_pgn_moves(self, game_node: chess.pgn.Game) -> str:
        """Извлекает PGN нотацию ходов"""
        try:
            return str(game_node.mainline_moves())
        except Exception:
            return str(game_node)
    
    def parse_batch(self, content: str, player_name: str, chunk_size: int = 100) -> List[Game]:
        """
        Парсит PGN по частям (для больших файлов)
        
        Args:
            content: PGN контент
            player_name: Имя игрока
            chunk_size: Размер чанка для парсинга
            
        Returns:
            List[Game]: Список игр
        """
        games = []
        pgn_stream = StringIO(content)
        
        chunk = []
        
        while True:
            try:
                game_node = chess.pgn.read_game(pgn_stream)
                if game_node is None:
                    break
                
                chunk.append(game_node)
                
                if len(chunk) >= chunk_size:
                    # Парсим чанк
                    for node in chunk:
                        try:
                            game = self.parse_single_game(node, player_name)
                            if game:
                                games.append(game)
                        except Exception as e:
                            self.logger.warning(f"Ошибка в чанке: {e}")
                    chunk = []
                    
            except Exception as e:
                self.logger.error(f"Ошибка в потоке PGN: {e}")
                break
        
        # Парсим остаток
        for node in chunk:
            try:
                game = self.parse_single_game(node, player_name)
                if game:
                    games.append(game)
            except Exception as e:
                self.logger.warning(f"Ошибка в остатке: {e}")
        
        return games