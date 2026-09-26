// static/js/core/board.js

class ChessBoard {
    constructor() {
        this.board = [];
        this.selectedCell = null;
        this.lastMove = { from: null, to: null };
        this.flipped = false;
    }
    
    init() {
        this.board = this.initialBoard();
    }
    
    initialBoard() {
        const board = [];
        const backRank = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R'];
        
        for (let r = 0; r < 8; r++) {
            board[r] = [];
            for (let c = 0; c < 8; c++) {
                if (r === 0) board[r][c] = backRank[c].toLowerCase();
                else if (r === 1) board[r][c] = 'p';
                else if (r === 6) board[r][c] = 'P';
                else if (r === 7) board[r][c] = backRank[c];
                else board[r][c] = null;
            }
        }
        return board;
    }
    
    getPiece(row, col) {
        return this.board[row]?.[col] || null;
    }
    
    setPiece(row, col, piece) {
        this.board[row][col] = piece;
    }
    
    movePiece(fromRow, fromCol, toRow, toCol) {
        const piece = this.getPiece(fromRow, fromCol);
        if (!piece) return false;
        
        this.setPiece(toRow, toCol, piece);
        this.setPiece(fromRow, fromCol, null);
        
        this.lastMove.from = { row: fromRow, col: fromCol };
        this.lastMove.to = { row: toRow, col: toCol };
        
        return true;
    }
    
    getFEN() {
        // Генерация FEN нотации для экспорта позиции
        let fen = '';
        for (let r = 0; r < 8; r++) {
            let empty = 0;
            for (let c = 0; c < 8; c++) {
                const piece = this.board[r][c];
                if (piece) {
                    if (empty > 0) {
                        fen += empty;
                        empty = 0;
                    }
                    fen += piece;
                } else {
                    empty++;
                }
            }
            if (empty > 0) fen += empty;
            if (r < 7) fen += '/';
        }
        return fen;
    }

    loadFromFEN(fen) {
        const parts = fen.split(' ');
        const rows = parts[0].split('/');
        this.board = [];
        
        for (let r = 0; r < 8; r++) {
            this.board[r] = [];
            let c = 0;
            for (const ch of rows[r]) {
                if (/\d/.test(ch)) {
                    const empty = parseInt(ch);
                    for (let i = 0; i < empty; i++) {
                        this.board[r][c++] = null;
                    }
                } else {
                    this.board[r][c++] = ch;
                }
            }
        }
        this.lastMove = { from: null, to: null };
    }

    setLastMoveFromAlgebraic(fromSq, toSq) {
        if (!fromSq || !toSq) {
            this.lastMove = { from: null, to: null };
            return;
        }
        // 'e2' → col=4, row=6  (шахматная нотация → индексы 8×8)
        const parse = (sq) => ({
            col: sq.charCodeAt(0) - 97,           // 'a'=0, 'b'=1, ...
            row: 8 - parseInt(sq[1]),              // '8'=0, '1'=7
        });
        this.lastMove.from = parse(fromSq);
        this.lastMove.to = parse(toSq);
    }

}

// Экспортируем экземпляр
