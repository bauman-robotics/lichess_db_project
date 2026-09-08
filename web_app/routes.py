"""
Маршруты веб-приложения
"""
import sys
from pathlib import Path
from datetime import datetime

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Optional, NumberRange

# Импортируем существующие сервисы
from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from services.lichess_client import LichessClient
from services.import_manager import ImportManager
from services.pgn_parser import PGNParser

main_bp = Blueprint('main', __name__)

# Формы
class PlayerSearchForm(FlaskForm):
    username = StringField('Имя игрока', validators=[DataRequired()])
    limit = IntegerField('Количество игр', default=100, validators=[Optional(), NumberRange(min=1, max=1000)])
    submit = SubmitField('Анализировать')


def get_player_stats(username: str) -> dict:
    """Получает статистику игрока из таблицы игрока"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = f"games_{username.lower()}"
    original_table = db.table_name
    db.table_name = table_name
    
    # Проверяем существование таблицы
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return {'exists': False, 'error': f'Таблица {table_name} не существует'}
    
    # Получаем статистику
    stats = db.get_table_stats()
    db.table_name = original_table
    db.close()
    
    # Проверяем, есть ли данные
    if not stats or stats.get('total_records', 0) == 0:
        return {
            'exists': True,
            'total': 0,
            'first_game': None,
            'last_game': None,
            'opponents': 0,
            'accuracy': 0,
            'results': {},
            'empty': True
        }
    
    # Формируем результат
    result_dist = {}
    for result, count in stats.get('results_distribution', []):
        result_dist[result] = count
    
    # Получаем точность, если есть
    accuracy = stats.get('avg_accuracy')
    if accuracy is None:
        # Пробуем вычислить вручную
        try:
            with db.connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT AVG(accuracy) FROM {table_name} WHERE accuracy IS NOT NULL")
                    accuracy = cur.fetchone()[0]
        except:
            accuracy = None
    
    return {
        'exists': True,
        'total': stats.get('total_records', 0),
        'first_game': stats.get('first_game'),
        'last_game': stats.get('last_game'),
        'opponents': stats.get('unique_opponents', 0),
        'accuracy': accuracy if accuracy is not None else 0,
        'results': result_dist
    }

def get_opening_stats(username: str, limit: int = 30) -> list:
    """Получает статистику по дебютам из таблицы игрока"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = f"games_{username.lower()}"
    original_table = db.table_name
    db.table_name = table_name
    
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return []
    
    results = []
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        opening_name,
                        COUNT(*) as games,
                        SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                        SUM(CASE WHEN result = 'Draw' THEN 1 ELSE 0 END) as draws,
                        ROUND(AVG(accuracy), 1) as avg_accuracy
                    FROM {table_name}
                    WHERE opening_name IS NOT NULL AND opening_name != ''
                    GROUP BY opening_name
                    HAVING COUNT(*) >= 1
                    ORDER BY games DESC
                    LIMIT %s;
                """, (limit,))
                
                for row in cur.fetchall():
                    # Принудительно создаем словарь с явным преобразованием типов
                    name = str(row[0]).strip() if row[0] else 'Неизвестно'
                    games = int(row[1]) if row[1] is not None else 0
                    wins = int(row[2]) if row[2] is not None else 0
                    losses = int(row[3]) if row[3] is not None else 0
                    draws = int(row[4]) if row[4] is not None else 0
                    accuracy = float(row[5]) if row[5] is not None else 0
                    win_rate = (wins / games * 100) if games > 0 else 0
                    
                    result_dict = {
                        'name': name,
                        'games': games,
                        'wins': wins,
                        'losses': losses,
                        'draws': draws,
                        'accuracy': accuracy,
                        'win_rate': win_rate
                    }
                    results.append(result_dict)
                    
    except Exception as e:
        print(f"ERROR in get_opening_stats: {e}")
        import traceback
        traceback.print_exc()
    
    db.table_name = original_table
    db.close()
    
    return results

def get_recent_games(username: str, limit: int = 10) -> list:
    """Получает последние игры игрока из таблицы игрока"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = f"games_{username.lower()}"
    original_table = db.table_name
    db.table_name = table_name
    
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return []
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT 
                    game_id,
                    game_date,
                    player_color,
                    opponent_name,
                    result,
                    accuracy,
                    move_count,
                    opening_name,
                    my_rating,
                    opponent_rating
                FROM {table_name}
                ORDER BY game_date DESC
                LIMIT %s;
            """, (limit,))
            
            results = []
            for row in cur.fetchall():
                results.append({
                    'game_id': row[0],
                    'date': row[1],
                    'color': row[2],
                    'opponent': row[3],
                    'result': row[4],
                    'accuracy': row[5],
                    'move_count': row[6],
                    'opening': row[7],
                    'my_rating': row[8],
                    'opponent_rating': row[9]
                })
    
    db.table_name = original_table
    db.close()
    return results


def get_all_players() -> list:
    """Получает список всех игроков в БД"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name LIKE 'games_%'
                ORDER BY table_name;
            """)
            players = [row[0][6:] for row in cur.fetchall()]
    
    db.close()
    return players

def get_rating_stats(username: str) -> dict:
    """Получает статистику по рейтингу"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = f"games_{username.lower()}"
    original_table = db.table_name
    db.table_name = table_name
    
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return {}
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            # Общая статистика
            cur.execute(f"""
                SELECT 
                    AVG(my_rating) as avg_rating,
                    MIN(my_rating) as min_rating,
                    MAX(my_rating) as max_rating,
                    AVG(opponent_rating) as avg_opp_rating
                FROM {table_name}
                WHERE my_rating > 0 AND opponent_rating > 0
            """)
            row = cur.fetchone()
            
            # Статистика по контролю времени с текущим рейтингом
            cur.execute(f"""
                WITH ranked_games AS (
                    SELECT 
                        time_control,
                        my_rating,
                        opponent_rating,
                        result,
                        game_date,
                        ROW_NUMBER() OVER (PARTITION BY time_control ORDER BY game_date DESC) as rn
                    FROM {table_name}
                    WHERE my_rating > 0 AND opponent_rating > 0
                ),
                time_stats AS (
                    SELECT 
                        time_control,
                        AVG(my_rating) as avg_rating,
                        MIN(my_rating) as min_rating,
                        MAX(my_rating) as max_rating,
                        AVG(opponent_rating) as avg_opp_rating,
                        COUNT(*) as games,
                        SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins
                    FROM {table_name}
                    WHERE my_rating > 0 AND opponent_rating > 0
                    GROUP BY time_control
                ),
                last_ratings AS (
                    SELECT 
                        time_control,
                        my_rating as last_rating,
                        game_date as last_game_date
                    FROM ranked_games
                    WHERE rn = 1
                )
                SELECT 
                    ts.time_control,
                    ts.avg_rating,
                    ts.min_rating,
                    ts.max_rating,
                    ts.avg_opp_rating,
                    ts.games,
                    ts.wins,
                    lr.last_rating,
                    lr.last_game_date
                FROM time_stats ts
                LEFT JOIN last_ratings lr ON ts.time_control = lr.time_control
                ORDER BY ts.games DESC
            """)
            
            rating_by_time = []
            for r in cur.fetchall():
                rating_by_time.append({
                    'time_control': r[0] if r[0] else 'Неизвестно',
                    'avg_rating': r[1] if r[1] else 0,
                    'min_rating': r[2] if r[2] else 0,
                    'max_rating': r[3] if r[3] else 0,
                    'avg_opponent_rating': r[4] if r[4] else 0,
                    'games': r[5] if r[5] else 0,
                    'wins': r[6] if r[6] else 0,
                    'last_rating': r[7] if r[7] else 0,
                    'last_game_date': r[8] if r[8] else None,
                    'win_rate': (r[6] / r[5] * 100) if r[5] and r[5] > 0 else 0
                })
            
            # Распределение по рейтингу соперников
            cur.execute(f"""
                SELECT 
                    CASE 
                        WHEN opponent_rating > my_rating + 100 THEN 'Сильнее на 100+'
                        WHEN opponent_rating > my_rating THEN 'Сильнее'
                        WHEN opponent_rating < my_rating - 100 THEN 'Слабее на 100+'
                        WHEN opponent_rating < my_rating THEN 'Слабее'
                        ELSE 'Равный'
                    END as category,
                    COUNT(*) as games,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins
                FROM {table_name}
                WHERE my_rating > 0 AND opponent_rating > 0
                GROUP BY category
            """)
            
            rating_results = []
            for r in cur.fetchall():
                rating_results.append({
                    'category': r[0],
                    'games': r[1],
                    'wins': r[2],
                    'win_rate': (r[2] / r[1] * 100) if r[1] > 0 else 0
                })
    
    db.table_name = original_table
    db.close()
    
    return {
        'avg_rating': row[0] if row and row[0] else 0,
        'min_rating': row[1] if row and row[1] else 0,
        'max_rating': row[2] if row and row[2] else 0,
        'avg_opponent_rating': row[3] if row and row[3] else 0,
        'by_time_control': rating_by_time,
        'by_category': rating_results
    }


def get_time_control_stats(username: str) -> list:
    """Статистика по контролю времени"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = f"games_{username.lower()}"
    original_table = db.table_name
    db.table_name = table_name
    
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return []
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT 
                    time_control,
                    COUNT(*) as games,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                    ROUND(AVG(accuracy), 1) as avg_accuracy
                FROM {table_name}
                GROUP BY time_control
                ORDER BY games DESC
                LIMIT 10
            """)
            
            results = []
            for row in cur.fetchall():
                results.append({
                    'time_control': row[0],
                    'games': row[1],
                    'wins': row[2],
                    'win_rate': (row[2] / row[1] * 100) if row[1] > 0 else 0,
                    'accuracy': row[3] if row[3] else 0
                })
    
    db.table_name = original_table
    db.close()
    return results


def get_rating_progression(username: str, limit: int = 30) -> list:
    """Прогресс рейтинга с дебютами"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = f"games_{username.lower()}"
    original_table = db.table_name
    db.table_name = table_name
    
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return []
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT 
                    game_date,
                    my_rating,
                    opponent_rating,
                    result,
                    opening_name,
                    player_color,
                    time_control
                FROM {table_name}
                WHERE my_rating > 0
                ORDER BY game_date DESC
                LIMIT %s
            """, (limit,))
            
            results = []
            for row in cur.fetchall():
                results.append({
                    'date': row[0] if row[0] else datetime.now(),
                    'my_rating': row[1] if row[1] else 0,
                    'opponent_rating': row[2] if row[2] else 0,
                    'result': row[3] if row[3] else '—',
                    'opening': row[4] if row[4] else '—',
                    'color': row[5] if row[5] else '—',
                    'time_control': row[6] if row[6] else '—'
                })
    
    db.table_name = original_table
    db.close()
    return results


def get_move_stats(username: str) -> dict:
    """Статистика по длине партий"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = f"games_{username.lower()}"
    original_table = db.table_name
    db.table_name = table_name
    
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return {}
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT 
                    AVG(move_count) as avg_moves,
                    MIN(move_count) as min_moves,
                    MAX(move_count) as max_moves,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY move_count) as median_moves
                FROM {table_name}
            """)
            row = cur.fetchone()
            
            # Распределение по длине
            cur.execute(f"""
                SELECT 
                    CASE 
                        WHEN move_count < 20 THEN 'Короткие (1-19)'
                        WHEN move_count < 40 THEN 'Средние (20-39)'
                        WHEN move_count < 60 THEN 'Длинные (40-59)'
                        ELSE 'Очень длинные (60+)'
                    END as category,
                    COUNT(*) as games,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins
                FROM {table_name}
                GROUP BY category
            """)
            
            distribution = []
            for r in cur.fetchall():
                distribution.append({
                    'category': r[0],
                    'games': r[1],
                    'wins': r[2],
                    'win_rate': (r[2] / r[1] * 100) if r[1] > 0 else 0
                })
    
    db.table_name = original_table
    db.close()
    
    return {
        'avg_moves': row[0] if row else 0,
        'min_moves': row[1] if row else 0,
        'max_moves': row[2] if row else 0,
        'median_moves': row[3] if row else 0,
        'distribution': distribution
    }

def download_player_games(username: str, limit: int = 1000) -> dict:
    """Скачивает игры игрока с Lichess и сохраняет в таблицу игрока"""
    try:
        config = ConfigLoader()
        lichess = LichessClient(config)
        
        pgn_content = lichess.download_games(
            username=username,
            max_games=limit
        )
        
        if not pgn_content:
            return {'success': False, 'error': 'Не удалось загрузить игры'}
        
        # Сохраняем во временный файл
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data/downloads/{username}_{timestamp}.pgn"
        
        Path("data/downloads").mkdir(parents=True, exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(pgn_content)
        
        # Импортируем в таблицу игрока
        db = DatabaseManager(config, 'local')
        
        # Создаем таблицу для игрока если не существует
        table_name = f"games_{username.lower()}"
        
        # Используем менеджер импорта
        import_manager = ImportManager(config, db)
        
        # Подменяем таблицу в db_manager для импорта
        original_table = db.table_name
        db.table_name = table_name
        
        # Проверяем существование таблицы
        if not db.table_exists():
            # Создаем таблицу используя схему
            from core.database.schema_loader import SchemaLoader
            schema_loader = SchemaLoader(config.get_schema_path())
            schema = schema_loader.load()
            schema.table_name = table_name
            
            # Создаем таблицу
            sql = schema_loader.get_create_table_sql(drop_existing=False)
            with db.connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    conn.commit()
            print(f"✅ Таблица {table_name} создана")
        
        # Импортируем
        result = import_manager.import_from_file(
            file_path=filename,
            player_name=username,
            delete_after_import=True
        )
        
        # Восстанавливаем имя таблицы
        db.table_name = original_table
        db.close()
        
        return {
            'success': True,
            'saved': result.get('saved_games', 0),
            'total': result.get('total_parsed', 0)
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


@main_bp.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@main_bp.route('/search', methods=['GET', 'POST'])
def search():
    """Поиск игрока"""
    form = PlayerSearchForm()
    
    if form.validate_on_submit():
        username = form.username.data.strip()
        limit = form.limit.data or 100
        
        # Используем жесткий путь с префиксом
        return redirect(f'/lichess-analyzer/player/{username}')
    
    return render_template('player_search.html', form=form)

@main_bp.route('/player/<username>')
def player_stats(username):
    """Страница статистики игрока"""
    stats = get_player_stats(username)
    
    if not stats.get('exists'):
        flash(f'Игрок {username} не найден в базе данных', 'warning')
        return render_template('player_stats.html', 
                             username=username, 
                             stats=None,
                             exists=False)
    
    # Получаем дополнительную статистику
    openings = get_opening_stats(username)
    games = get_recent_games(username)
    rating_stats = get_rating_stats(username)
    time_stats = get_time_control_stats(username)
    move_stats = get_move_stats(username)
    rating_progression = get_rating_progression(username, limit=30)
    
    # Преобразуем даты в строки для JSON
    rating_progression_json = []
    for game in rating_progression:
        game_copy = {}
        for key, value in game.items():
            if isinstance(value, datetime):
                game_copy[key] = value.strftime('%Y-%m-%d')
            elif value is None:
                game_copy[key] = 0
            else:
                game_copy[key] = value
        rating_progression_json.append(game_copy)
    
    return render_template('player_stats.html',
                         username=username,
                         stats=stats,
                         exists=True,
                         openings=openings,
                         games=games,
                         rating_stats=rating_stats,
                         time_stats=time_stats,
                         move_stats=move_stats,
                         rating_progression=rating_progression,
                         rating_progression_json=rating_progression_json)

@main_bp.route('/player/<username>/download')
def download_player(username):
    """Скачивает игры игрока"""
    result = download_player_games(username)
    
    if result.get('success'):
        flash(f'✅ Загружено {result["saved"]} игр для {username}', 'success')
    else:
        flash(f'❌ Ошибка: {result.get("error", "Неизвестная ошибка")}', 'danger')
    
    return redirect(url_for('main.player_stats', username=username))


# Закомментированные маршруты (можно раскомментировать позже)
# @main_bp.route('/players')
# def players_list():
#     """Список игроков"""
#     players = get_all_players()
#     return render_template('players_list.html', players=players)


# @main_bp.route('/compare', methods=['GET', 'POST'])
# def compare():
#     """Сравнение игроков"""
#     form = CompareForm()
    
#     if form.validate_on_submit():
#         player1 = form.player1.data.strip()
#         player2 = form.player2.data.strip()
        
#         return redirect(url_for('main.compare_results', player1=player1, player2=player2))
    
#     return render_template('compare_players.html', form=form)


# Форма сравнения
class CompareForm(FlaskForm):
    player1 = StringField('Первый игрок', validators=[DataRequired()])
    player2 = StringField('Второй игрок', validators=[DataRequired()])
    submit = SubmitField('Сравнить')


# @main_bp.route('/compare/<player1>/<player2>')
# def compare_results(player1, player2):
#     """Результаты сравнения"""
#     stats1 = get_player_stats(player1)
#     stats2 = get_player_stats(player2)
    
#     if not stats1.get('exists') or not stats2.get('exists'):
#         flash('Один из игроков не найден', 'danger')
#         return redirect(url_for('main.compare'))
    
#     # Сравнение
#     comparison = {}
#     for key in ['total', 'opponents', 'accuracy']:
#         v1 = stats1.get(key, 0) or 0
#         v2 = stats2.get(key, 0) or 0
#         comparison[key] = {
#             'diff': v1 - v2,
#             'p1': v1,
#             'p2': v2
#         }
    
#     # Процент побед
#     win_rate1 = stats1['results'].get('Win', 0) / stats1['total'] * 100 if stats1['total'] > 0 else 0
#     win_rate2 = stats2['results'].get('Win', 0) / stats2['total'] * 100 if stats2['total'] > 0 else 0
#     comparison['win_rate'] = {
#         'diff': win_rate1 - win_rate2,
#         'p1': win_rate1,
#         'p2': win_rate2
#     }
    
#     return render_template('compare_results.html',
#                          player1=player1,
#                          player2=player2,
#                          stats1=stats1,
#                          stats2=stats2,
#                          comparison=comparison)