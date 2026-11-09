
from fastapi import Request


def trusted_client_ip(request: Request) -> str:
    """
    Доверенный IP клиента.

    Порядок:
      1. X-Real-IP — ставит nginx как $remote_addr.
         Этот заголовок перезаписывается nginx, клиент не может его подделать.
      2. X-Forwarded-For[-1] — последний hop, добавленный нашим nginx.
         Первый элемент X-Forwarded-For может быть подделан клиентом,
         потому что nginx использует $proxy_add_x_forwarded_for.
      3. request.client.host — fallback для прямого доступа мимо nginx.
    """
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()

    xff = request.headers.get('X-Forwarded-For')
    if xff:
        return xff.split(',')[-1].strip()

    if request.client:
        return request.client.host

    return 'unknown'