import json
from datetime import datetime
from src.utils import logger, save_json

def consolidate_market_data(processed_pools, output_dir="cache/prices"):
    """
    Consolida dados de múltiplas DEXs em uma estrutura unificada (market_prices_map.json).
    """
    market_prices_map = {}
    
    for pool in processed_pools:
        pair_id = pool['pair_id']
        dex = pool['dex']
        
        if pair_id not in market_prices_map:
            market_prices_map[pair_id] = {}
        
        # Adiciona ou atualiza os dados da DEX para o par
        market_prices_map[pair_id][dex] = {
            "token0": pool['token0'],
            "token1": pool['token1'],
            "reserve0": pool['reserves']['token0'],
            "reserve1": pool['reserves']['token1'],
            "price": pool['price'],
            "active": pool['active'],
            "last_update": pool['last_update']
        }
    
    filepath = os.path.join(output_dir, "market_prices_map.json")
    save_json(market_prices_map, filepath)
    logger.info(f"Market prices map gerado em: {filepath}")
    return market_prices_map
