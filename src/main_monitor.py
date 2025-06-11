import os
import time
import argparse
import asyncio
from datetime import datetime
from src.utils import setup_logging, load_settings, load_json, save_json
from src.pool_processor import process_pool_files
from src.market_consolidator import consolidate_market_data
from src.swap_fetcher import fetch_recent_swaps, save_recent_swaps
from src.web_generator import generate_html_table, create_responsive_interface

# Carrega as configurações iniciais
settings = load_settings()
logger = setup_logging(
    log_dir=os.path.join(settings.get("CACHE_DIR", "cache"), "logs"),
    log_level=settings.get("LOG_LEVEL", "INFO")
)

async def run_full_update():
    """Executa o pipeline completo de atualização."""
    logger.info("Iniciando atualização completa do monitor DEX...")

    cache_dir = settings.get("CACHE_DIR", "cache")
    output_dir = settings.get("OUTPUT_DIR", "output")
    
    # 1. Processamento de Pools Locais
    logger.info("Etapa 1: Processando arquivos de pools locais...")
    # Para testar, você precisará criar alguns arquivos JSON de pool em cache/pools/
    # Ex: cache/pools/pools_taco_20250610.json
    # { "token0": "WAX", "token1": "TACO", "reserve0": 1000.0, "reserve1": 2000.0, "src": "swap.taco" }
    processed_pools = process_pool_files(
        cache_dir=os.path.join(cache_dir, "pools"),
        min_reserve_threshold=settings.get("MIN_RESERVE_THRESHOLD", 1.0)
    )
    logger.info(f"Processadas {len(processed_pools)} pools.")

    # 2. Geração do Market Prices Map
    logger.info("Etapa 2: Consolidando dados para o Market Prices Map...")
    market_data = consolidate_market_data(
        processed_pools,
        output_dir=os.path.join(cache_dir, "prices")
    )
    logger.info(f"Market Prices Map gerado com {len(market_data)} pares.")

    # 3. Consulta de Swaps Históricos
    logger.info("Etapa 3: Buscando swaps históricos recentes...")
    recent_swaps = await fetch_recent_swaps(
        contracts=settings.get("SWAP_CONTRACTS", []),
        hyperion_api=settings.get("HYPERION_API"),
        hours_back=settings.get("TIME_WINDOW_HOURS", 24),
        limit=100 # Limite de ações por chamada de contrato
    )
    save_recent_swaps(recent_swaps, output_dir=os.path.join(cache_dir, "swaps"))
    logger.info(f"Capturados {len(recent_swaps)} swaps recentes.")

    # 4. Interface Web Dinâmica
    logger.info("Etapa 4: Gerando interface web dinâmica...")
    create_responsive_interface(output_dir=output_dir) # Cria CSS/JS
    generate_html_table(market_data, output_dir=output_dir) # Gera HTML com dados
    logger.info("Interface web gerada com sucesso.")

    logger.info("Atualização completa concluída.")

async def main():
    parser = argparse.ArgumentParser(description="WAX DEX Monitor System")
    parser.add_argument("--process-pools", action="store_true", help="Process local pool files.")
    parser.add_argument("--fetch-swaps", action="store_true", help="Fetch recent historical swaps.")
    parser.add_argument("--generate-web", action="store_true", help="Generate the web interface.")
    parser.add_argument("--full-update", action="store_true", help="Run the full update pipeline.")
    parser.add_argument("--monitor", action="store_true", help="Run in continuous monitoring mode.")
    parser.add_argument("--interval", type=int, default=settings.get("UPDATE_INTERVAL_MINUTES", 5),
                        help="Interval in minutes for continuous monitoring.")

    args = parser.parse_args()

    if args.process_pools:
        processed_pools = process_pool_files(
            cache_dir=os.path.join(settings.get("CACHE_DIR", "cache"), "pools"),
            min_reserve_threshold=settings.get("MIN_RESERVE_THRESHOLD", 1.0)
        )
        consolidate_market_data(processed_pools, output_dir=os.path.join(settings.get("CACHE_DIR", "cache"), "prices"))
    elif args.fetch_swaps:
        recent_swaps = await fetch_recent_swaps(
            contracts=settings.get("SWAP_CONTRACTS", []),
            hyperion_api=settings.get("HYPERION_API"),
            hours_back=settings.get("TIME_WINDOW_HOURS", 24)
        )
        save_recent_swaps(recent_swaps, output_dir=os.path.join(settings.get("CACHE_DIR", "cache"), "swaps"))
    elif args.generate_web:
        market_data = load_json(os.path.join(settings.get("CACHE_DIR", "cache"), "prices", "market_prices_map.json"))
        if market_data:
            create_responsive_interface(output_dir=settings.get("OUTPUT_DIR", "output"))
            generate_html_table(market_data, output_dir=settings.get("OUTPUT_DIR", "output"))
        else:
            logger.warning("market_prices_map.json não encontrado ou vazio. Não foi possível gerar a interface web.")
    elif args.full_update:
        await run_full_update()
    elif args.monitor:
        interval_seconds = args.interval * 60
        logger.info(f"Iniciando monitoramento contínuo a cada {args.interval} minutos...")
        while True:
            await run_full_update()
            logger.info(f"Aguardando {args.interval} minutos para a próxima atualização...")
            await asyncio.sleep(interval_seconds)
    else:
        parser.print_help()

if __name__ == "__main__":
    # Cria os diretórios iniciais se não existirem
    os.makedirs(settings.get("CACHE_DIR", "cache"), exist_ok=True)
    os.makedirs(os.path.join(settings.get("CACHE_DIR", "cache"), "pools"), exist_ok=True)
    os.makedirs(os.path.join(settings.get("CACHE_DIR", "cache"), "prices"), exist_ok=True)
    os.makedirs(os.path.join(settings.get("CACHE_DIR", "cache"), "swaps"), exist_ok=True)
    os.makedirs(os.path.join(settings.get("CACHE_DIR", "cache"), "logs"), exist_ok=True)
    os.makedirs(settings.get("OUTPUT_DIR", "output"), exist_ok=True)
    os.makedirs(os.path.join(settings.get("OUTPUT_DIR", "output"), "assets"), exist_ok=True)
    os.makedirs("config", exist_ok=True) # Garante que a pasta config existe para settings.json

    asyncio.run(main())
