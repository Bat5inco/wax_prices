import logging
import os
import json
import asyncio
import aiohttp
from aiohttp_retry import RetryClient, ExponentialRetry
from datetime import datetime

# Configuração de logging
def setup_logging(log_dir="cache/logs", log_level="INFO"):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"monitor_{datetime.now().strftime('%Y%m%d')}.log")

    # Remove handlers existentes para evitar duplicação
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging() # Inicializa com valores padrão, será reconfigurado pelo main_monitor

async def safe_api_call(session, url, retries=3, timeout=10):
    """
    Chamada de API assíncrona com retry logic.
    """
    retry_options = ExponentialRetry(attempts=retries)
    retry_client = RetryClient(client_session=session, retry_options=retry_options)
    
    try:
        async with retry_client.get(url, timeout=timeout) as response:
            response.raise_for_status()
            return await response.json()
    except aiohttp.ClientError as e:
        logger.error(f"Erro na chamada da API para {url}: {e}")
        return None
    except asyncio.TimeoutError:
        logger.error(f"Timeout na chamada da API para {url}")
        return None

def load_settings(config_path="config/settings.json"):
    """Carrega as configurações do arquivo settings.json."""
    try:
        with open(config_path, 'r') as f:
            settings = json.load(f)
        return settings
    except FileNotFoundError:
        logger.error(f"Arquivo de configuração não encontrado: {config_path}")
        return {}
    except json.JSONDecodeError:
        logger.error(f"Erro ao decodificar JSON no arquivo de configuração: {config_path}")
        return {}

def save_json(data, filepath):
    """Salva dados em um arquivo JSON."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Dados salvos em: {filepath}")
    except IOError as e:
        logger.error(f"Erro ao salvar arquivo {filepath}: {e}")

def load_json(filepath):
    """Carrega dados de um arquivo JSON."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Dados carregados de: {filepath}")
        return data
    except FileNotFoundError:
        logger.warning(f"Arquivo não encontrado: {filepath}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao decodificar JSON de {filepath}: {e}")
        return None
