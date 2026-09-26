// static/js/ui/renderer.js

class BoardRenderer {
    constructor(boardManager, arrowSystem = null) {
        this.board = boardManager;
        this.arrows = arrowSystem;
        this.selectedCell = null;
        this.piecesSvg = PIECES_SVG; // из pieces.js
    }
    
    render() {
        const boardEl = document.getElementById('chessBoard');
        boardEl.innerHTML = '';
        
        const rows = this.board.flipped ? [7,6,5,4,3,2,1,0] : [0,1,2,3,4,5,6,7];
        const cols = this.board.flipped ? [7,6,5,4,3,2,1,0] : [0,1,2,3,4,5,6,7];
        
        for (let ri = 0; ri < 8; ri++) {
            const r = rows[ri];
            for (let ci = 0; ci < 8; ci++) {
                const c = cols[ci];
                const cell = this.createCell(r, c);
                boardEl.appendChild(cell);
            }
        }
        
        // Рисуем стрелки поверх (если система подключена)
        if (this.arrows) {
            this.arrows.render();
        }
    }
    
    createCell(row, col) {
        const cell = document.createElement('div');
        const isWhite = (row + col) % 2 === 0;
        cell.className = `chess-cell ${isWhite ? 'white' : 'black'}`;
        
        // Подсветка выбранной клетки
        if (this.selectedCell && this.selectedCell.row === row && this.selectedCell.col === col) {
            cell.classList.add('selected');
        }
        
        // Подсветка последнего хода
        if (this.board.lastMove.from && 
            this.board.lastMove.from.row === row && 
            this.board.lastMove.from.col === col) {
            cell.classList.add('last-move-from');
        }
        if (this.board.lastMove.to && 
            this.board.lastMove.to.row === row && 
            this.board.lastMove.to.col === col) {
            cell.classList.add('last-move-to');
        }
        
        // Фигура
        const piece = this.board.getPiece(row, col);
        if (piece) {
            const svgContent = this.piecesSvg[piece] || '';
            if (svgContent) {
                const wrapper = document.createElement('div');
                wrapper.style.width = '100%';
                wrapper.style.height = '100%';
                wrapper.style.display = 'flex';
                wrapper.style.alignItems = 'center';
                wrapper.style.justifyContent = 'center';
                wrapper.style.padding = '10%';
                wrapper.innerHTML = svgContent;
                cell.appendChild(wrapper);
            }
        }
        
        cell.dataset.row = row;
        cell.dataset.col = col;
        
        // Передаём события дальше
        cell.addEventListener('click', () => this.onCellClick(row, col));
        cell.addEventListener('mousedown', (e) => this.onCellMouseDown(e, row, col));
        cell.addEventListener('mousemove', (e) => this.onCellMouseMove(e, row, col));
        cell.addEventListener('mouseup', (e) => this.onCellMouseUp(e, row, col));
        
        return cell;
    }
    
    onCellClick(row, col) {
        // Обработка кликов для ходов
        // Будет переопределено в app.js
        if (this.clickHandler) {
            this.clickHandler(row, col);
        }
    }
    
    onCellMouseDown(e, row, col) {
        // Передаём в систему стрелок
        if (window.arrowSystem) {
            window.arrowSystem.onMouseDown(e, row, col);
        }
    }
    
    onCellMouseMove(e, row, col) {
        if (window.arrowSystem) {
            window.arrowSystem.onMouseMove(e, row, col);
        }
    }
    
    onCellMouseUp(e, row, col) {
        if (window.arrowSystem) {
            window.arrowSystem.onMouseUp(e, row, col);
        }
    }
    
    setClickHandler(handler) {
        this.clickHandler = handler;
    }
}