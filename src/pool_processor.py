import os
import json
from datetime import datetime
from src.utils import logger, save_json, load_json

def validate_pool_data(pool_data):
    """
    Valida a estrutura e os valores dos dados de pool.
    Retorna True se válido, False caso contrário.
    """
    required_fields = ['token0', 'token1', 'reserve0', 'reserve1', 'src']
    if not all(field in pool_data for field in required_fields):
        logger.warning(f"Dados de pool inválidos: campos obrigatórios ausentes em {pool_data}")
        return False
    
    if not isinstance(pool_data['reserve0'], (int, float)) or not isinstance(pool_data['reserve1'], (int, float)):
        logger.warning(f"Reservas inválidas (não numéricas): {pool_data}")
        return False
    
    return True

def calculate_price(reserve0, reserve1):
    """
    Calcula o preço: reserve1 / (reserve0 + 1e-8) para evitar divisão por zero.
    """
    if reserve0 <= 0: # Evita divisão por zero ou por valores muito pequenos
        return 0.0
    return reserve1 / (reserve0 + 1e-8)

def normalize_token_pair(token0_symbol, token1_symbol):
    """
    Normaliza a ordem dos tokens (alfabética) e retorna o par e um flag de inversão.
    """
    if token0_symbol < token1_symbol:
        return f"{token0_symbol}_{token1_symbol}", False # Não invertido
    else:
        return f"{token1_symbol}_{token0_symbol}", True # Invertido

def process_pool_files(cache_dir="cache/pools", min_reserve_threshold=1.0):
    """
    Processa todos os arquivos pools_*.json no diretório cache/pools.
    Valida dados, normaliza tokens, calcula preços e filtra pools com reservas baixas.
    Retorna uma lista de pools processadas.
    """
    processed_pools = []
    pool_files = [f for f in os.listdir(cache_dir) if f.startswith('pools_') and f.endswith('.json')]
    
    if not pool_files:
        logger.warning(f"Nenhum arquivo de pool encontrado em {cache_dir}.")
        return []

    for filename in pool_files:
        filepath = os.path.join(cache_dir, filename)
        logger.info(f"Processando arquivo de pool: {filepath}")
        pools_data = load_json(filepath)

        if not pools_data:
            continue

        for pool in pools_data:
            if not validate_pool_data(pool):
                continue

            token0_symbol = pool['token0']
            token1_symbol = pool['token1']
            reserve0 = float(pool['reserve0'])
            reserve1 = float(pool['reserve1'])
            src = pool['src']
            
            # Filtrar pools com reservas muito baixas
            if reserve0 < min_reserve_threshold or reserve1 < min_reserve_threshold:
                logger.debug(f"Pool filtrada por baixa reserva: {token0_symbol}/{token1_symbol} em {src}")
                continue

            # Normaliza o par e verifica se foi invertido
            normalized_pair_id, was_inverted = normalize_token_pair(token0_symbol, token1_symbol)

            # Calcula o preço. Se o par foi invertido, o preço calculado é de token0 por token1.
            # Precisamos que o preço seja sempre de token2 por token1 (onde token1 < token2).
            calculated_price = calculate_price(reserve0, reserve1)
            
            # Se o par original era (token1, token0) e o canônico é (token0, token1),
            # então o preço calculado (reserve1/reserve0) é token0 por token1.
            # Se o par original era (token0, token1) e o canônico é (token0, token1),
            # então o preço calculado (reserve1/reserve0) é token1 por token0.
            # A regra é: price = amount_tokenB / amount_tokenA.
            # Se tokenA é o primeiro do par canônico e tokenB é o segundo, o preço está ok.
            # Se tokenA é o segundo do par canônico e tokenB é o primeiro, o preço precisa ser invertido.

            # Para garantir que o preço seja sempre do segundo token canônico pelo primeiro
            # Ex: TACO_WAX -> WAX por TACO
            final_price = calculated_price
            if was_inverted: # Se o par original era (token1, token0) e o canônico é (token0, token1)
                # O preço calculado é token0 por token1. Precisamos de token1 por token0.
                # Ex: se original era WAX/TACO (reserve0=WAX, reserve1=TACO), price=TACO/WAX.
                # Canônico é TACO/WAX. Queremos WAX/TACO. Então inverte.
                final_price = 1 / (calculated_price + 1e-8) if calculated_price > 0 else 0.0

            processed_pools.append({
                "pair_id": normalized_pair_id,
                "dex": src,
                "token0": {
                    "symbol": token0_symbol,
                    "contract": pool.get('token0_contract', 'unknown'), # Adiciona contrato e precisão se disponível
                    "precision": pool.get('token0_precision', 8)
                },
                "token1": {
                    "symbol": token1_symbol,
                    "contract": pool.get('token1_contract', 'unknown'),
                    "precision": pool.get('token1_precision', 8)
                },
                "reserves": {
                    "token0": reserve0,
                    "token1": reserve1
                },
                "price": final_price,
                "active": True, # Assumimos ativo se passou pelos filtros
                "last_update": datetime.utcnow().isoformat() + "Z"
            })
    return processed_pools
