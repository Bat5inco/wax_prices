import requests
from datetime import datetime, timedelta
import json
import os
import re
import pandas as pd

# --- Configurações ---
HYPERION_API = "https://api.wax.alohaeos.com/v2/history/get_actions"
CONTRACTS = ["swap.taco", "alcordexmain", "swap.alcor", "swap.box"]
MINUTES_BACK = 60 # Filtrar ações dos últimos 60 minutos

# --- Funções Principais ---

def fetch_swaps(contract, limit=100):
    """
    Busca ações de 'transfer' para um contrato DEX específico no Hyperion API.
    Filtra por memos contendo 'deposit' e dentro do período de tempo.
    Extrai tokenA, amount_tokenA (o que foi enviado para o DEX)
    e tenta extrair tokenB, amount_tokenB (o que foi recebido do DEX) do memo.
    """
    url = f"{HYPERION_API}?account={contract}&filter=transfer&limit={limit}"
    print(f"Buscando dados de {contract}...")
    try:
        response = requests.get(url, timeout=10) # Adiciona timeout para evitar travamentos
        response.raise_for_status() # Levanta um erro para códigos de status HTTP ruins (4xx ou 5xx)
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar dados de {contract}: {e}")
        return []

    actions = response.json().get('actions', [])
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=MINUTES_BACK)

    swaps_data = []
    for action in actions:
        act = action.get("act", {})
        data = act.get("data", {})
        
        # Filtra por transferências *para* o contrato DEX com "deposit" no memo
        memo = data.get("memo", "")
        if data.get("to") != contract or "deposit" not in memo.lower():
            continue
        
        try:
            timestamp = datetime.fromisoformat(action["@timestamp"].replace("Z", "+00:00"))
        except ValueError:
            print(f"Timestamp inválido: {action.get('@timestamp')}")
            continue

        if timestamp <= cutoff:
            continue

        # Extrai tokenA e amount_tokenA da própria ação de transferência (o que foi depositado)
        quantity_str = data.get("quantity", "")
        if not quantity_str:
            continue
        
        try:
            amount_tokenA = float(quantity_str.split(" ")[0])
            tokenA = quantity_str.split(" ")[1]
        except (ValueError, IndexError):
            print(f"Não foi possível analisar a quantidade: {quantity_str}")
            continue

        # Extrai tokenB e amount_tokenB do memo
        # Procura por padrões "QUANTIDADE TOKEN" no memo
        memo_pairs = re.findall(r"(\d+\.\d+)\s+([A-Z]+)", memo)
        
        amount_tokenB = None
        tokenB = None

        # Tenta encontrar o token que NÃO é tokenA no memo
        for amt_str, tok_str in memo_pairs:
            if tok_str != tokenA: 
                try:
                    amount_tokenB = float(amt_str)
                    tokenB = tok_str
                    break 
                except ValueError:
                    continue
        
        # Se tokenB ou amount_tokenB não puderam ser encontrados, pula esta ação
        if amount_tokenB is None or tokenB is None:
            # print(f"Não foi possível extrair tokenB/amount_tokenB do memo: {memo}")
            continue

        swaps_data.append({
            "contract": contract,
            "tokenA": tokenA, # Token enviado para o DEX
            "amount_tokenA": amount_tokenA,
            "tokenB": tokenB, # Token recebido do DEX
            "amount_tokenB": amount_tokenB,
            "timestamp": timestamp.isoformat()
        })
    return swaps_data

def normalize_data(raw_swaps, output_dir="normalized"):
    """
    Normaliza os dados de swap, calcula preços e unifica pares invertidos.
    Salva os dados normalizados em um arquivo JSON.
    """
    os.makedirs(output_dir, exist_ok=True)
    normalized_records = []

    for swap in raw_swaps:
        tokenA_orig = swap["tokenA"] # Token enviado
        amount_tokenA_orig = swap["amount_tokenA"]
        tokenB_orig = swap["tokenB"] # Token recebido
        amount_tokenB_orig = swap["amount_tokenB"]
        contract = swap["contract"]

        # Calcula o preço de tokenB_orig em termos de tokenA_orig
        # Preço = (quantidade recebida) / (quantidade enviada)
        price_of_B_per_A = amount_tokenB_orig / (amount_tokenA_orig + 0.00000001)

        # Determina o nome canônico do par (ordem alfabética)
        canonical_token1 = min(tokenA_orig, tokenB_orig)
        canonical_token2 = max(tokenA_orig, tokenB_orig)
        canonical_pair_name = f"{canonical_token1}/{canonical_token2}"
        
        # Ajusta o preço para ser consistente com o nome canônico do par.
        # O preço final será sempre de canonical_token2 por canonical_token1.
        final_price = price_of_B_per_A
        if tokenA_orig == canonical_token2 and tokenB_orig == canonical_token1:
            # Se o swap original foi (canonical_token2 enviado) -> (canonical_token1 recebido),
            # então price_of_B_per_A é o preço de canonical_token1 em canonical_token2.
            # Precisamos inverter para obter o preço de canonical_token2 em canonical_token1.
            final_price = 1 / (price_of_B_per_A + 0.00000001)

        normalized_records.append({
            "pair": canonical_pair_name,
            "source": contract,
            "price": final_price,
            "timestamp": swap["timestamp"]
        })
    
    # Salva os dados normalizados em um arquivo JSON
    filename = os.path.join(output_dir, f"normalized_swaps_{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
    with open(filename, 'w') as f:
        json.dump(normalized_records, f, indent=2)
    
    return normalized_records

def process_data(normalized_data):
    """
    Processa os dados normalizados para criar uma tabela dinâmica de preços.
    """
    df = pd.DataFrame(normalized_data)
    
    if df.empty:
        print("Nenhum dado normalizado para processar.")
        return pd.DataFrame()

    # Converte timestamp para datetime para ordenação
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Ordena por timestamp para obter o preço mais recente para cada combinação par-fonte
    df = df.sort_values(by='timestamp', ascending=False)
    df = df.drop_duplicates(subset=['pair', 'source'], keep='first')

    # Pivota a tabela para ter as DEXs como colunas
    pivot_table = df.pivot_table(index='pair', columns='source', values='price', aggfunc='first')
    
    # Preenche valores NaN (pares não encontrados em certas DEXs)
    pivot_table = pivot_table.fillna('N/A') 

    return pivot_table

def generate_html_table(processed_data, output_file="output/tabela_dinamica.html"):
    """
    Gera um arquivo HTML com a tabela de preços dinâmica e funcionalidade de busca.
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Gera os cabeçalhos da tabela (DEXs)
    table_headers = "".join([f"<th>{col}</th>" for col in processed_data.columns]) if not processed_data.empty else ""

    # Gera as linhas da tabela
    table_rows = ""
    if not processed_data.empty:
        for idx, row in processed_data.iterrows():
            row_cells = "".join([f"<td>{val:.8f}</td>" if isinstance(val, (float)) and val != 'N/A' else f"<td>{val}</td>" for val in row])
            table_rows += f"<tr><td>{idx}</td>{row_cells}</tr>"
    else:
        # Mensagem de "No hay datos" se a tabela estiver vazia
        colspan_val = len(CONTRACTS) + 1 # Número de colunas: Par + todas as DEXs
        table_rows = f'<tr class="no-results"><td colspan="{colspan_val}">No hay datos disponibles.</td></tr>'

    html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DEX Monitor - Tabela de Preços</title>
    <style>
        body {{ font-family: sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }}
        .container {{ max-width: 900px; margin: 0 auto; background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ text-align: center; color: #0056b3; }}
        .search-container {{ margin-bottom: 20px; text-align: center; }}
        .search-container input {{ width: 80%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 16px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #007bff; color: white; cursor: pointer; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        tr:hover {{ background-color: #f1f1f1; }}
        .no-results {{ text-align: center; color: #888; padding: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>DEX Monitor - Tabela de Preços</h1>
        <div class="search-container">
            <input type="text" id="searchInput" onkeyup="filterTable()" placeholder="Buscar por token...">
        </div>
        <table id="priceTable">
            <thead>
                <tr>
                    <th>Par</th>
                    {table_headers}
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </div>

    <script>
        function filterTable() {{
            var input, filter, table, tr, td, i, txtValue;
            input = document.getElementById("searchInput");
            filter = input.value.toUpperCase();
            table = document.getElementById("priceTable");
            tr = table.getElementsByTagName("tr");
            var foundResults = false;

            // Itera sobre todas as linhas da tabela, começando da segunda (pula o cabeçalho)
            for (i = 1; i < tr.length; i++) {{ 
                // Verifica se a linha é a mensagem "No hay datos disponibles"
                if (tr[i].classList.contains('no-results')) {{
                    continue; // Pula a linha de mensagem
                }}

                var rowVisible = false;
                // Verifica a coluna 'Par' (primeira td)
                td = tr[i].getElementsByTagName("td")[0];
                if (td) {{
                    txtValue = td.textContent || td.innerText;
                    if (txtValue.toUpperCase().indexOf(filter) > -1) {{
                        rowVisible = true;
                    }}
                }}
                
                if (rowVisible) {{
                    tr[i].style.display = "";
                    foundResults = true;
                }} else {{
                    tr[i].style.display = "none";
                }}
            }}

            // Mostra/esconde a mensagem "No hay datos"
            var noResultsRow = document.querySelector('.no-results');
            if (noResultsRow) {{
                if (foundResults || filter === '') {{
                    noResultsRow.style.display = 'none';
                }} else {{
                    noResultsRow.style.display = '';
                }}
            }}
        }}
    </script>
</body>
</html>
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Tabela HTML gerada em {output_file}")

def main():
    """
    Função principal para executar o monitor DEX.
    """
    # Cria diretórios se não existirem
    os.makedirs("data", exist_ok=True)
    os.makedirs("normalized", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    all_raw_swaps = []
    for contract in CONTRACTS:
        raw_swaps = fetch_swaps(contract)
        all_raw_swaps.extend(raw_swaps)
        
        # Salva dados brutos (opcional, para depuração/persistência)
        raw_filename = os.path.join("data", f"raw_swaps_{contract}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
        with open(raw_filename, 'w') as f:
            json.dump(raw_swaps, f, indent=2)
        print(f"Salvos {len(raw_swaps)} swaps brutos de {contract} para {raw_filename}")

    if not all_raw_swaps:
        print("Nenhum swap encontrado. Gerando tabela vazia.")
        # Gera uma tabela vazia se não houver dados
        generate_html_table(pd.DataFrame(columns=['pair'] + CONTRACTS))
        return

    print("Normalizando dados...")
    normalized_data = normalize_data(all_raw_swaps)
    print(f"Normalizados {len(normalized_data)} registros.")

    if not normalized_data:
        print("Nenhum dado normalizado após o processamento. Gerando tabela vazia.")
        generate_html_table(pd.DataFrame(columns=['pair'] + CONTRACTS))
        return

    print("Processando dados para geração da tabela...")
    processed_table = process_data(normalized_data)
    
    print("Gerando tabela HTML...")
    generate_html_table(processed_table)
    print("Processo concluído.")

if __name__ == "__main__":
    main()
