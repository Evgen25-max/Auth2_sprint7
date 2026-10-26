
import os

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DEFAULT_HANDLERS = ['console', 'file']
LOG_FILE = os.getenv('LOG_FILE', 'logs/auth.log')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': LOG_FORMAT},
        'access': {
            '()': 'uvicorn.logging.AccessFormatter',
            'fmt': "%(levelprefix)s %(client_addr)s - '%(request_line)s' %(status_code)s",
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_FILE,
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        'access': {
            'formatter': 'access',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
        },
    },
    'loggers': {
        'services.auth': {'level': 'DEBUG', 'handlers': LOG_DEFAULT_HANDLERS, 'propagate': False},
        'services.rbac': {'level': 'DEBUG', 'handlers': LOG_DEFAULT_HANDLERS, 'propagate': False},
        'api.v1.auth': {'level': 'DEBUG', 'handlers': LOG_DEFAULT_HANDLERS, 'propagate': False},
        'api.deps': {'level': 'DEBUG', 'handlers': LOG_DEFAULT_HANDLERS, 'propagate': False},
        'sqlalchemy.engine': {'level': 'WARNING', 'propagate': False},
        'watchfiles': {'level': 'WARNING', 'propagate': False},
        'uvicorn.error': {'level': 'INFO'},
        'uvicorn.access': {'handlers': ['access'], 'level': 'INFO', 'propagate': False},
    },
    'root': {'level': 'INFO', 'formatter': 'verbose', 'handlers': LOG_DEFAULT_HANDLERS},
}
