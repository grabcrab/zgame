bind = "0.0.0.0:5001"
workers = 4                    # Количество worker-процессов
worker_class = "sync"          # Синхронные workers
worker_connections = 1000      # Подключений на worker
max_requests = 1000           # Перезапуск worker после N запросов
max_requests_jitter = 50      # Случайный jitter
timeout = 300                 # Таймаут запроса
keepalive = 5                 # Keep-alive соединения
preload_app = True           # Предзагрузка приложения