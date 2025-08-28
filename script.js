// script.js
class DiceGame {
    constructor() {
        this.tg = window.Telegram.WebApp;
        this.user = null;
        this.currentGame = null;
        this.activeGames = [];
        
        this.init();
    }

    async init() {
        try {
            // Инициализация Telegram WebApp
            this.tg.expand();
            this.tg.enableClosingConfirmation();
            
            // Загрузка пользователя
            await this.loadUserData();
            
            // Инициализация интерфейса
            this.initUI();
            
            // Загрузка активных игр
            await this.loadActiveGames();
            
            // Показываем главный экран
            this.showScreen('mainScreen');
            
        } catch (error) {
            console.error('Ошибка инициализации:', error);
            this.showError('Не удалось загрузить игру');
        }
    }

    async loadUserData() {
        try {
            // Здесь будет запрос к боту для получения данных пользователя
            // Временно используем заглушку
            this.user = {
                id: this.tg.initDataUnsafe.user?.id || Math.floor(Math.random() * 1000000),
                username: this.tg.initDataUnsafe.user?.username || 'user',
                balance: 1000,
                wins: 0,
                losses: 0
            };
            
            this.updateBalanceDisplay();
            
        } catch (error) {
            console.error('Ошибка загрузки данных пользователя:', error);
            throw error;
        }
    }

    async loadActiveGames() {
        try {
            // Здесь будет запрос к боту для получения активных игр
            // Временно используем заглушку
            this.activeGames = [
                { id: 1, bet: 100, players: 1, maxPlayers: 2, creator: 'user1' },
                { id: 2, bet: 200, players: 2, maxPlayers: 3, creator: 'user2' },
                { id: 3, bet: 500, players: 3, maxPlayers: 4, creator: 'user3' }
            ];
            
            this.updateGamesList();
            
        } catch (error) {
            console.error('Ошибка загрузки активных игр:', error);
        }
    }

    initUI() {
        // Основные кнопки
        document.getElementById('createGameBtn').addEventListener('click', () => this.showScreen('createGameScreen'));
        document.getElementById('findGameBtn').addEventListener('click', () => this.showFindGame());
        document.getElementById('profileBtn').addEventListener('click', () => this.showProfile());
        document.getElementById('addBalanceBtn').addEventListener('click', () => this.showDepositModal());

        // Кнопки назад
        document.getElementById('backFromCreate').addEventListener('click', () => this.showScreen('mainScreen'));
        document.getElementById('backFromLobby').addEventListener('click', () => this.showScreen('mainScreen'));
        document.getElementById('backToMainBtn').addEventListener('click', () => this.showScreen('mainScreen'));

        // Создание игры
        document.getElementById('createGameBtnConfirm').addEventListener('click', () => this.createGame());

        // Пополнение баланса
        document.getElementById('confirmDepositBtn').addEventListener('click', () => this.processDeposit());
        document.getElementById('closeDepositModal').addEventListener('click', () => this.hideDepositModal());

        // Предложения ставок
        document.querySelectorAll('.bet-suggestion').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const bet = e.target.getAttribute('data-bet');
                document.getElementById('betAmount').value = bet;
            });
        });

        // Предложения сумм пополнения
        document.querySelectorAll('.amount-suggestion').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const amount = e.target.getAttribute('data-amount');
                document.getElementById('depositAmount').value = amount;
            });
        });

        // Бросок костей
        document.getElementById('rollDiceBtn').addEventListener('click', () => this.rollDice());

        // Выход из лобби
        document.getElementById('leaveLobbyBtn').addEventListener('click', () => this.leaveLobby());
    }

    showScreen(screenId) {
        // Скрываем все экраны
        document.querySelectorAll('.screen').forEach(screen => {
            screen.classList.add('hidden');
        });

        // Показываем нужный экран
        const screen = document.getElementById(screenId);
        if (screen) {
            screen.classList.remove('hidden');
            
            // Обновляем данные при показе определенных экранов
            if (screenId === 'mainScreen') {
                this.updateBalanceDisplay();
                this.updateGamesList();
            }
        }
    }

    updateBalanceDisplay() {
        if (this.user) {
            document.getElementById('balance').textContent = this.user.balance.toLocaleString();
        }
    }

    updateGamesList() {
        const gamesList = document.getElementById('gamesList');
        gamesList.innerHTML = '';

        if (this.activeGames.length === 0) {
            gamesList.innerHTML = '<div class="text-center">Нет активных игр</div>';
            return;
        }

        this.activeGames.forEach(game => {
            const gameElement = document.createElement('div');
            gameElement.className = 'game-item';
            gameElement.innerHTML = `
                <div class="game-bet">${game.bet} ⭐</div>
                <div>Игроков: ${game.players}/${game.maxPlayers}</div>
                <div>Создатель: @${game.creator}</div>
            `;
            gameElement.addEventListener('click', () => this.joinGame(game.id));
            gamesList.appendChild(gameElement);
        });
    }

    async createGame() {
        try {
            const playersCount = document.querySelector('input[name="players"]:checked').value;
            const betAmount = parseInt(document.getElementById('betAmount').value);

            if (betAmount < 10) {
                this.showError('Минимальная ставка - 10 звезд');
                return;
            }

            if (this.user.balance < betAmount) {
                this.showError('Недостаточно звезд для создания игры');
                this.showDepositModal();
                return;
            }

            // Здесь будет запрос к боту для создания игры
            const gameId = Math.floor(Math.random() * 1000);
            
            this.currentGame = {
                id: gameId,
                bet: betAmount,
                players: 1,
                maxPlayers: parseInt(playersCount),
                status: 'waiting'
            };

            // Обновляем баланс (временно)
            this.user.balance -= betAmount;
            this.updateBalanceDisplay();

            this.showLobbyScreen();

        } catch (error) {
            console.error('Ошибка создания игры:', error);
            this.showError('Не удалось создать игру');
        }
    }

    showLobbyScreen() {
        if (!this.currentGame) return;

        document.getElementById('lobbyId').textContent = this.currentGame.id;
        document.getElementById('lobbyBet').textContent = this.currentGame.bet;
        document.getElementById('lobbyPlayers').textContent = this.currentGame.players;
        document.getElementById('lobbyMaxPlayers').textContent = this.currentGame.maxPlayers;
        document.getElementById('lobbyStatus').textContent = 'Ожидание';

        this.updatePlayersList();

        this.showScreen('lobbyScreen');
    }

    updatePlayersList() {
        const playersList = document.getElementById('playersList');
        playersList.innerHTML = '';

        // Добавляем создателя
        const creatorElement = document.createElement('div');
        creatorElement.className = 'player-item';
        creatorElement.innerHTML = `
            <div class="player-avatar">👑</div>
            <div class="player-info">
                <div class="player-name">@${this.user.username} (Вы)</div>
                <div class="player-status">Готов</div>
            </div>
        `;
        playersList.appendChild(creatorElement);

        // Кнопка начала игры
        const startBtn = document.getElementById('startGameBtn');
        if (this.currentGame.players === this.currentGame.maxPlayers) {
            startBtn.disabled = false;
        } else {
            startBtn.disabled = true;
        }
    }

    async joinGame(gameId) {
        try {
            // Находим игру
            const game = this.activeGames.find(g => g.id === gameId);
            if (!game) {
                this.showError('Игра не найдена');
                return;
            }

            if (this.user.balance < game.bet) {
                const missing = game.bet - this.user.balance;
                this.showError(`Недостаточно звезд. Нужно еще: ${missing} ⭐`);
                this.showDepositModal();
                return;
            }

            // Здесь будет запрос к боту для присоединения к игре
            this.currentGame = { ...game };
            this.currentGame.players++;

            // Обновляем баланс (временно)
            this.user.balance -= game.bet;
            this.updateBalanceDisplay();

            this.showLobbyScreen();

        } catch (error) {
            console.error('Ошибка присоединения к игре:', error);
            this.showError('Не удалось присоединиться к игре');
        }
    }

    async startGame() {
        try {
            if (!this.currentGame) return;

            // Здесь будет запрос к боту для начала игры
            this.showGameScreen();

        } catch (error) {
            console.error('Ошибка начала игры:', error);
            this.showError('Не удалось начать игру');
        }
    }

    showGameScreen() {
        if (!this.currentGame) return;

        document.getElementById('gameId').textContent = this.currentGame.id;
        document.getElementById('gameBet').textContent = this.currentGame.bet;

        this.showScreen('gameScreen');
    }

    async rollDice() {
        try {
            const diceBtn = document.getElementById('rollDiceBtn');
            diceBtn.disabled = true;

            // Анимация броска костей
            const dice = document.getElementById('dice');
            dice.style.animation = 'diceRoll 2s ease-out';

            // Генерируем случайный результат
            const result = Math.floor(Math.random() * 6) + 1;
            
            // Обновляем отображение результата
            setTimeout(() => {
                dice.textContent = this.getDiceEmoji(result);
                document.getElementById('yourDice').textContent = result;
                
                // Здесь будет логика определения победителя
                this.showGameResult(result);
                
            }, 2000);

        } catch (error) {
            console.error('Ошибка броска костей:', error);
            this.showError('Не удалось бросить кости');
        }
    }

    getDiceEmoji(value) {
        const diceEmojis = ['⚀', '⚁', '⚂', '⚃', '⚄', '⚅'];
        return diceEmojis[value - 1] || '🎲';
    }

    showGameResult(yourResult) {
        // Временная реализация - просто показываем результат
        const resultElement = document.getElementById('gameResult');
        const winnerInfo = document.getElementById('winnerInfo');
        const prizeInfo = document.getElementById('prizeInfo');
        
        // Здесь будет реальная логика определения победителя
        const isWinner = Math.random() > 0.5;
        const prize = this.currentGame.bet * this.currentGame.maxPlayers * 0.95; // -5% комиссия
        
        if (isWinner) {
            winnerInfo.textContent = '🎉 Вы победили!';
            prizeInfo.textContent = `💰 Вы выиграли: ${Math.floor(prize)} ⭐`;
            
            // Обновляем баланс
            this.user.balance += Math.floor(prize);
            this.user.wins++;
        } else {
            winnerInfo.textContent = '😢 Вы проиграли';
            prizeInfo.textContent = 'Попробуйте еще раз!';
            this.user.losses++;
        }
        
        this.updateBalanceDisplay();
        resultElement.classList.remove('hidden');
    }

    showDepositModal() {
        document.getElementById('depositModal').classList.remove('hidden');
    }

    hideDepositModal() {
        document.getElementById('depositModal').classList.add('hidden');
    }

    async processDeposit() {
        try {
            const amount = parseInt(document.getElementById('depositAmount').value);
            
            if (amount < 10) {
                this.showError('Минимальная сумма пополнения - 10 звезд');
                return;
            }

            // Здесь будет интеграция с Telegram Stars платежами
            // Временно просто добавляем сумму к балансу
            this.user.balance += amount;
            this.updateBalanceDisplay();
            
            this.hideDepositModal();
            this.showSuccess(`Баланс пополнен на ${amount} ⭐`);

        } catch (error) {
            console.error('Ошибка пополнения баланса:', error);
            this.showError('Не удалось пополнить баланс');
        }
    }

    async leaveLobby() {
        try {
            if (!this.currentGame) return;

            // Здесь будет запрос к боту для выхода из лобби
            // Возвращаем ставку
            this.user.balance += this.currentGame.bet;
            this.updateBalanceDisplay();

            this.currentGame = null;
            this.showScreen('mainScreen');
            this.showSuccess('Вы покинули лобби');

        } catch (error) {
            console.error('Ошибка выхода из лобби:', error);
            this.showError('Не удалось покинуть лобби');
        }
    }

    showFindGame() {
        if (this.activeGames.length === 0) {
            this.showInfo('В настоящее время нет активных игр');
            return;
        }
        
        // Показываем список игр
        this.updateGamesList();
    }

    showProfile() {
        const profileText = `
            👤 Ваш профиль:
            
            💰 Баланс: ${this.user.balance} ⭐
            🏆 Побед: ${this.user.wins}
            💔 Поражений: ${this.user.losses}
            📊 Винрейт: ${this.calculateWinRate()}%
        `;
        
        this.showInfo(profileText);
    }

    calculateWinRate() {
        const totalGames = this.user.wins + this.user.losses;
        if (totalGames === 0) return 0;
        return ((this.user.wins / totalGames) * 100).toFixed(1);
    }

    showError(message) {
        this.tg.showPopup({
            title: 'Ошибка',
            message: message,
            buttons: [{ type: 'ok' }]
        });
    }

    showSuccess(message) {
        this.tg.showPopup({
            title: 'Успех',
            message: message,
            buttons: [{ type: 'ok' }]
        });
    }

    showInfo(message) {
        this.tg.showPopup({
            title: 'Информация',
            message: message,
            buttons: [{ type: 'ok' }]
        });
    }
}

// Инициализация игры при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    // Скрываем экран загрузки через 2 секунды
    setTimeout(() => {
        document.getElementById('loadingScreen').classList.add('hidden');
        new DiceGame();
    }, 2000);
});

// Обработка платежей через Telegram Stars
if (window.Telegram && window.Telegram.WebApp) {
    window.Telegram.WebApp.onEvent('invoiceClosed', (event) => {
        if (event.status === 'paid') {
            // Обработка успешной оплаты
            console.log('Платеж успешно завершен');
        }
    });
}