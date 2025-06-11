import os
import json
from src.utils import logger, save_json, load_json

def generate_html_table(market_data, output_dir="output"):
    """
    Gera a tabela HTML dinâmica com dados de preços.
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "assets"), exist_ok=True)

    # Extrai todas as DEXs únicas para os cabeçalhos da tabela
    all_dexes = sorted(list(set(dex for pair_data in market_data.values() for dex in pair_data.keys())))
    
    # Cabeçalhos da tabela
    table_headers = "".join([f"<th>{dex.replace('swap.', '').upper()}</th>" for dex in all_dexes])
    table_headers += "<th>Melhor Preço</th><th>Volume 24h (Placeholder)</th><th>Última Atualização</th>"

    # Linhas da tabela
    table_rows = ""
    if not market_data:
        table_rows = f'<tr class="no-results"><td colspan="{len(all_dexes) + 4}">No hay datos disponibles.</td></tr>'
    else:
        for pair_id, dex_data in market_data.items():
            row_cells = ""
            best_price = float('inf')
            best_dex = "N/A"
            
            # Preenche as colunas de DEX
            for dex in all_dexes:
                if dex in dex_data and dex_data[dex]['active']:
                    price = dex_data[dex]['price']
                    row_cells += f"<td>{price:.8f}</td>"
                    if price < best_price:
                        best_price = price
                        best_dex = dex.replace('swap.', '').upper()
                else:
                    row_cells += "<td>N/A</td>"
            
            # Adiciona a coluna de Melhor Preço
            if best_price != float('inf'):
                row_cells += f"<td>{best_price:.8f} ({best_dex})</td>"
            else:
                row_cells += "<td>N/A</td>"

            # Adiciona colunas de placeholder para Volume e Última Atualização
            # Volume 24h e Fees 24h não são calculados neste escopo, então são placeholders
            row_cells += "<td>0 WAX</td>" # Placeholder para Volume 24h
            
            # Última atualização (pega a mais recente entre as DEXs do par)
            latest_update = "N/A"
            if dex_data:
                timestamps = [datetime.fromisoformat(d['last_update'].replace('Z', '+00:00')) for d in dex_data.values()]
                if timestamps:
                    latest_update = max(timestamps).strftime('%H:%M:%S')
            row_cells += f"<td>{latest_update}</td>"

            table_rows += f"<tr><td>{pair_id.replace('_', '/')}</td>{row_cells}</tr>"

    html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WAX DEX Monitor</title>
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
    <div class="container">
        <h1>WAX DEX Monitor</h1>
        <div class="search-container">
            <input type="text" id="searchInput" onkeyup="filterTable()" placeholder="Buscar por par de token (ex: WAX/TACO)...">
        </div>
        <table id="dexTable">
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
    <script src="assets/script.js"></script>
</body>
</html>
    """
    
    index_html_path = os.path.join(output_dir, "index.html")
    with open(index_html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    logger.info(f"Interface web gerada em: {index_html_path}")

def create_responsive_interface(output_dir="output"):
    """
    Cria os arquivos CSS e JS para a interface web.
    """
    style_css_path = os.path.join(output_dir, "assets", "style.css")
    script_js_path = os.path.join(output_dir, "assets", "script.js")

    style_css_content = """
body { 
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
    margin: 0; 
    padding: 20px; 
    background-color: #1a1a2e; 
    color: #e0e0e0; 
    line-height: 1.6;
}
.container { 
    max-width: 1200px; 
    margin: 20px auto; 
    background-color: #2a2a4a; 
    padding: 30px; 
    border-radius: 10px; 
    box-shadow: 0 5px 15px rgba(0,0,0,0.3); 
}
h1 { 
    text-align: center; 
    color: #00bcd4; 
    margin-bottom: 30px; 
    font-size: 2.5em;
}
.search-container { 
    margin-bottom: 25px; 
    text-align: center; 
}
.search-container input { 
    width: 70%; 
    padding: 12px 15px; 
    border: 1px solid #4a4a6a; 
    border-radius: 5px; 
    font-size: 1em; 
    background-color: #3a3a5a; 
    color: #e0e0e0; 
    transition: border-color 0.3s ease;
}
.search-container input::placeholder {
    color: #a0a0c0;
}
.search-container input:focus {
    border-color: #00bcd4;
    outline: none;
}
table { 
    width: 100%; 
    border-collapse: collapse; 
    margin-top: 20px; 
    background-color: #3a3a5a; 
    border-radius: 8px; 
    overflow: hidden;
}
th, td { 
    border: 1px solid #4a4a6a; 
    padding: 15px; 
    text-align: left; 
    vertical-align: middle;
}
th { 
    background-color: #007bff; 
    color: white; 
    cursor: pointer; 
    font-weight: bold; 
    text-transform: uppercase; 
    font-size: 0.9em;
}
th:hover {
    background-color: #0056b3;
}
tbody tr:nth-child(even) { 
    background-color: #303050; 
}
tbody tr:hover { 
    background-color: #404060; 
    transition: background-color 0.2s ease;
}
.no-results { 
    text-align: center; 
    color: #888; 
    padding: 20px; 
    background-color: #3a3a5a;
}

/* Responsive Design */
@media (max-width: 768px) {
    .container {
        margin: 10px;
        padding: 15px;
    }
    h1 {
        font-size: 1.8em;
    }
    .search-container input {
        width: 95%;
    }
    table, thead, tbody, th, td, tr {
        display: block;
    }
    thead tr {
        position: absolute;
        top: -9999px;
        left: -9999px;
    }
    tr { 
        border: 1px solid #4a4a6a; 
        margin-bottom: 10px;
        border-radius: 8px;
        overflow: hidden;
    }
    td { 
        border: none;
        border-bottom: 1px solid #4a4a6a; 
        position: relative;
        padding-left: 50%;
        text-align: right;
    }
    td:last-child {
        border-bottom: 0;
    }
    td:before {
        position: absolute;
        top: 0;
        left: 6px;
        width: 45%;
        padding-right: 10px;
        white-space: nowrap;
        text-align: left;
        font-weight: bold;
        color: #00bcd4;
    }
    /* Labeling the cells for mobile */
    td:nth-of-type(1):before { content: "Par:"; }
    td:nth-of-type(2):before { content: "Swap.Taco:"; }
    td:nth-of-type(3):before { content: "Alcor:"; }
    td:nth-of-type(4):before { content: "DefiBox:"; }
    td:nth-of-type(5):before { content: "NeftyBlocks:"; }
    td:nth-of-type(6):before { content: "Melhor Preço:"; }
    td:nth-of-type(7):before { content: "Volume 24h:"; }
    td:nth-of-type(8):before { content: "Última Atualização:"; }
}
    """
    with open(style_css_path, 'w', encoding='utf-8') as f:
        f.write(style_css_content)
    logger.info(f"CSS gerado em: {style_css_path}")

    script_js_content = """
function filterTable() {
    var input, filter, table, tr, td, i, txtValue;
    input = document.getElementById("searchInput");
    filter = input.value.toUpperCase();
    table = document.getElementById("dexTable");
    tr = table.getElementsByTagName("tr");
    var foundResults = false;

    // Loop through all table rows, and hide those who don't match the search query
    for (i = 1; i < tr.length; i++) { // Start from 1 to skip the header row
        if (tr[i].classList.contains('no-results')) {
            continue; // Skip the "No hay datos" row
        }
        td = tr[i].getElementsByTagName("td")[0]; // Get the first TD (Pair column)
        if (td) {
            txtValue = td.textContent || td.innerText;
            if (txtValue.toUpperCase().indexOf(filter) > -1) {
                tr[i].style.display = "";
                foundResults = true;
            } else {
                tr[i].style.display = "none";
            }
        }       
    }

    // Show/hide the "No hay datos" message
    var noResultsRow = document.querySelector('.no-results');
    if (noResultsRow) {
        if (foundResults || filter === '') {
            noResultsRow.style.display = 'none';
        } else {
            noResultsRow.style.display = '';
        }
    }
}

// Basic sorting functionality (client-side)
document.addEventListener('DOMContentLoaded', function() {
    const getCellValue = (tr, idx) => tr.children[idx].innerText || tr.children[idx].textContent;

    const comparer = (idx, asc) => (a, b) => ((v1, v2) => 
        v1 !== '' && v2 !== '' && !isNaN(v1) && !isNaN(v2) ? v1 - v2 : v1.toString().localeCompare(v2)
    )(getCellValue(asc ? a : b, idx), getCellValue(asc ? b : a, idx));

    document.querySelectorAll('th').forEach(th => th.addEventListener('click', (() => {
        const table = th.closest('table');
        const tbody = table.querySelector('tbody');
        Array.from(tbody.querySelectorAll('tr:not(.no-results)'))
            .sort(comparer(Array.from(th.parentNode.children).indexOf(th), this.asc = !this.asc))
            .forEach(tr => tbody.appendChild(tr));
    })));
});
    """
    with open(script_js_path, 'w', encoding='utf-8') as f:
        f.write(script_js_content)
    logger.info(f"JavaScript gerado em: {script_js_path}")
