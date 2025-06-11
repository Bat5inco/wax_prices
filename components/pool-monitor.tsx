"use client"

import { useState, useEffect, useCallback, useMemo } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Download } from "lucide-react"
import { Button } from "@/components/ui/button"

// --- Constantes de Configuração ---
const API_GET_TABLE_ROWS = "https://api.wax.alohaeos.com/v1/chain/get_table_rows"
const CONTRACTS_TO_MONITOR = [
  { id: "swap.taco", name: "Taco Swap", table: "pairs" }, // Taco usa 'pairs'
  { id: "swap.alcor", name: "Alcor DEX", table: "pools" }, // Alcor usa 'pools'
  { id: "swap.box", name: "DefiBox", table: "pairs" }, // DefiBox usa 'swap.box'
]

// --- Tipos de Dados ---
interface PoolDataRow {
  id: number
  // Campos que podem variar muito em estrutura, então usamos 'any' e tratamos no parsing
  token_a?: any // e.g., "8,WAX" (string)
  token_b?: any // e.g., "8,TACO" (string)
  reserve_a?: any // e.g., "1000.00000000 WAX" (string)
  reserve_b?: any // e.g., "2000.00000000 TACO" (string)
  token_a_contract?: string // Contrato do token A (se separado)
  token_b_contract?: string // Contrato do token B (se separado)

  // Campos específicos para 'pools' tables (Alcor)
  token0?: any // Pode ser { contract, symbol, precision } (Alcor) ou { ticker, contract, precision, amount } (DefiBox)
  token1?: any // Idem token0
  reserve0?: any // Pode ser { quantity, ... } (Alcor) ou um número (DefiBox)
  reserve1?: any // Idem reserve0

  // Outros campos que podem estar presentes
  source?: string // Para DefiBox (pode não estar presente em todos os casos)
  pair?: number // Para DefiBox
  price?: number | null // Para DefiBox (pode ser null)

  [key: string]: any // Para outras propriedades desconhecidas
}

interface CachedContractData {
  contract: string
  table: string
  timestamp: string
  total_rows: number
  data: PoolDataRow[]
}

interface Filters {
  contract: string // 'all' | contract_id
  minLiquidity: number
  maxLiquidity: number
  tokenSearch: string
  activeOnly: boolean
  sortBy: "liquidity" | "volume" | "price" | "pair"
  sortOrder: "desc" | "asc"
}

interface NormalizedPool {
  id: number
  contract: string // Contrato da DEX (ex: swap.taco)
  pair: string // e.g., "WAX/TACO"
  token0_symbol: string // Símbolo do token A
  token1_symbol: string // Símbolo do token B
  token0_contract: string // Endereço do contrato do token A
  token1_contract: string // Endereço do contrato do token B
  reserve0_amount: number // Quantidade do token A na pool
  reserve1_amount: number // Quantidade do token B na pool
  liquidity: number
  price: number // Preço de token1_symbol por token0_symbol
  volume24h: number // Placeholder
  last_update: string // Timestamp da coleta ou da pool
  [key: string]: any
}

// --- Funções Utilitárias ---
const parseTokenString = (tokenStr: string | undefined | null): { precision: number; symbol: string } => {
  const safeTokenStr = tokenStr || ""
  if (safeTokenStr === "") {
    return { precision: 0, symbol: "" }
  }

  const parts = safeTokenStr.split(",")
  if (parts.length === 2) {
    const precision = Number.parseInt(parts[0])
    return { precision: isNaN(precision) ? 0 : precision, symbol: parts[1] }
  }
  return { precision: 0, symbol: safeTokenStr } // Assume que é apenas o símbolo
}

const parseReserveString = (reserveStr: string | undefined | null): { amount: number; symbol: string } => {
  const safeReserveStr = reserveStr || ""
  if (safeReserveStr === "") {
    return { amount: 0, symbol: "" }
  }

  const parts = safeReserveStr.split(" ")
  if (parts.length === 2) {
    const amount = Number.parseFloat(parts[0])
    return { amount: isNaN(amount) ? 0 : amount, symbol: parts[1] }
  }
  const amountOnly = Number.parseFloat(safeReserveStr)
  if (!isNaN(amountOnly)) {
    return { amount: amountOnly, symbol: "" } // Apenas quantidade
  }
  return { amount: 0, symbol: safeReserveStr } // Apenas símbolo
}

const calculateLiquidity = (reserve0: number, reserve1: number) => {
  return reserve0 + reserve1
}

const calculatePrice = (reserve0: number, reserve1: number) => {
  return reserve1 / (reserve0 + 0.00000001) // Adiciona um pequeno valor para evitar divisão por zero
}

const normalizePairName = (symbolA: string, symbolB: string) => {
  const sortedSymbols = [symbolA, symbolB].sort()
  return `${sortedSymbols[0]}/${sortedSymbols[1]}`
}

// --- Componente Principal ---
const PoolMonitor = () => {
  const [cachedData, setCachedData] = useState<{ [key: string]: CachedContractData | null }>({})
  const [lastUpdate, setLastUpdate] = useState<{ [key: string]: string | null }>({})
  const [filters, setFilters] = useState<Filters>({
    contract: "all",
    minLiquidity: 0,
    maxLiquidity: Number.POSITIVE_INFINITY,
    tokenSearch: "",
    activeOnly: false,
    sortBy: "liquidity",
    sortOrder: "desc",
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // --- Fetching Data ---
  const fetchAndCachePoolData = useCallback(async (contractId: string, table: string) => {
    const allRows: PoolDataRow[] = []
    let nextKey: string | number = ""
    let hasMore = true
    let attempts = 0
    const maxAttempts = 5 // Para evitar loops infinitos em caso de erro de paginação

    while (hasMore && attempts < maxAttempts) {
      try {
        const payload = {
          json: true,
          code: contractId,
          scope: contractId, // Este pode ser o problema para swap.box (DefiBox)
          table: table,
          limit: 5000,
          lower_bound: nextKey,
        }

        // Log do payload para depuração
        console.log(`Fetching payload for ${contractId}:`, JSON.stringify(payload, null, 2))

        const response = await fetch(API_GET_TABLE_ROWS, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })

        if (!response.ok) {
          throw new Error(`HTTP error! Status: ${response.status} for contract ${contractId}`)
        }

        const data = await response.json()
        allRows.push(...data.rows)
        hasMore = data.more
        nextKey = data.next_key

        // Delay anti-rate-limit
        if (hasMore) {
          await new Promise((resolve) => setTimeout(resolve, 250))
        }
        attempts = 0 // Reseta tentativas em caso de sucesso
      } catch (err: any) {
        console.error(`Erro ao buscar dados de ${contractId} (tentativa ${attempts + 1}):`, err.message || err)
        attempts++
        if (attempts >= maxAttempts) {
          throw new Error(
            `Falha ao carregar dados de ${contractId} após ${maxAttempts} tentativas: ${err.message || err}`,
          )
        }
        await new Promise((resolve) => setTimeout(resolve, 1000 * attempts)) // Backoff exponencial
      }
    }

    const cacheData: CachedContractData = {
      contract: contractId,
      table,
      timestamp: new Date().toISOString(),
      total_rows: allRows.length,
      data: allRows,
    }

    setCachedData((prev) => ({
      ...prev,
      [contractId]: cacheData,
    }))

    setLastUpdate((prev) => ({
      ...prev,
      [contractId]: new Date().toISOString(),
    }))

    return allRows
  }, [])

  const updateAllPoolData = useCallback(async () => {
    setLoading(true)
    setError(null) // Limpa erros anteriores
    const errors: string[] = []

    const results = await Promise.allSettled(CONTRACTS_TO_MONITOR.map((c) => fetchAndCachePoolData(c.id, c.table)))

    results.forEach((result, index) => {
      if (result.status === "rejected") {
        const contractId = CONTRACTS_TO_MONITOR[index].id
        errors.push(`Erro para ${contractId}: ${result.reason.message || result.reason}`)
        setCachedData((prev) => ({ ...prev, [contractId]: null })) // Define como null para indicar falha
        setLastUpdate((prev) => ({ ...prev, [contractId]: null }))
      }
    })

    if (errors.length > 0) {
      setError(`Erros ao carregar dados: ${errors.join("; ")}`)
    }
    setLoading(false)
  }, [fetchAndCachePoolData])

  // --- Efeito para carregar dados na montagem ---
  useEffect(() => {
    updateAllPoolData()
  }, [updateAllPoolData])

  // --- Lógica de Processamento e Filtragem ---
  const getFilteredPoolData = useMemo(() => {
    const allPools: NormalizedPool[] = []

    Object.entries(cachedData).forEach(([contractId, data]) => {
      if (data && data.data) {
        const contractPools = data.data.map((pool) => {
          // Descomente para depurar a estrutura de dados bruta de cada pool
          // console.log(`Processing pool from ${contractId}:`, pool);

          let token0_symbol = ""
          let token1_symbol = ""
          let token0_contract_address = "unknown"
          let token1_contract_address = "unknown"
          let reserve0_amount = 0
          let reserve1_amount = 0

          if (contractId === "swap.alcor") {
            // Estrutura da tabela 'pools' do Alcor
            token0_symbol = pool.token0?.symbol || ""
            token1_symbol = pool.token1?.symbol || ""
            token0_contract_address = pool.token0?.contract || "unknown"
            token1_contract_address = pool.token1?.contract || "unknown"
            reserve0_amount = parseReserveString(pool.reserve0?.quantity).amount
            reserve1_amount = parseReserveString(pool.reserve1?.quantity).amount
          } else if (contractId === "swap.box") {
            // Lógica específica para DefiBox (swap.box)
            // Log para depuração da estrutura de dados do swap.box
            console.log(`Raw pool data for swap.box:`, pool)

            token0_symbol = pool.token0?.ticker || ""
            token1_symbol = pool.token1?.ticker || ""
            token0_contract_address = pool.token0?.contract || "unknown"
            token1_contract_address = pool.token1?.contract || "unknown"
            // As reservas são números diretos, não strings ou objetos com 'quantity'
            reserve0_amount = typeof pool.reserve0 === "number" ? pool.reserve0 : 0
            reserve1_amount = typeof pool.reserve1 === "number" ? pool.reserve1 : 0
          } else if (contractId === "swap.taco") {
            // Lógica específica para TacoSwap
            // Estrutura da tabela 'pairs' do TacoSwap
            const parsedTokenA = parseTokenString(pool.token_a)
            const parsedTokenB = parseTokenString(pool.token_b)

            token0_symbol = parsedTokenA.symbol
            token1_symbol = parsedTokenB.symbol
            token0_contract_address = pool.token_a_contract || "unknown"
            token1_contract_address = pool.token_b_contract || "unknown"
            reserve0_amount = parseReserveString(pool.reserve_a).amount
            reserve1_amount = parseReserveString(pool.reserve_b).amount
          } else {
            // Fallback para outros contratos ou estruturas inesperadas
            const parsedTokenA = parseTokenString(pool.token_a)
            const parsedTokenB = parseTokenString(pool.token_b)

            token0_symbol = parsedTokenA.symbol
            token1_symbol = parsedTokenB.symbol
            token0_contract_address = pool.token0_contract || pool.token_a_contract || "unknown"
            token1_contract_address = pool.token1_contract || pool.token_b_contract || "unknown"
            reserve0_amount = parseReserveString(pool.reserve_a).amount
            reserve1_amount = parseReserveString(pool.reserve_b).amount
          }

          const normalizedPair = normalizePairName(token0_symbol, token1_symbol)
          const liquidity = calculateLiquidity(reserve0_amount, reserve1_amount)
          const price = calculatePrice(reserve0_amount, reserve1_amount) // Preço de tokenB por tokenA

          // Descomente para depurar os valores parseados
          // console.log(`Parsed values for ${contractId}: Pair=${normalizedPair}, Token0=${token0_symbol} (${token0_contract_address}), Token1=${token1_symbol} (${token1_contract_address}), Reserves=${reserve0_amount}/${reserve1_amount}, Price=${price}`);

          return {
            id: pool.id,
            contract: contractId, // Contrato da DEX
            pair: normalizedPair,
            token0_symbol: token0_symbol, // Ticker do token A
            token1_symbol: token1_symbol, // Ticker do token B
            token0_contract: token0_contract_address, // Endereço do contrato do token A
            token1_contract: token1_contract_address, // Endereço do contrato do token B
            reserve0_amount: reserve0_amount, // Quantidade do token A
            reserve1_amount: reserve1_amount, // Quantidade do token B
            liquidity: liquidity,
            price: price,
            volume24h: pool.volume24h || pool.volume_24h || 0, // Placeholder
            last_update: new Date().toISOString(), // Usar timestamp da coleta ou da pool se disponível
            original_pool_data: pool, // Manter dados originais para depuração
          }
        })
        allPools.push(...contractPools)
      }
    })

    // Aplicar filtros
    const filtered = allPools.filter((pool) => {
      // Filtro por contrato da DEX
      if (filters.contract !== "all" && pool.contract !== filters.contract) {
        return false
      }

      // Filtro por busca de token (símbolo ou par)
      if (filters.tokenSearch) {
        const searchLower = filters.tokenSearch.toLowerCase()
        if (
          !pool.token0_symbol.toLowerCase().includes(searchLower) &&
          !pool.token1_symbol.toLowerCase().includes(searchLower) &&
          !pool.pair.toLowerCase().includes(searchLower)
        ) {
          return false
        }
      }

      // Filtro por liquidez
      if (pool.liquidity < filters.minLiquidez || pool.liquidity > filters.maxLiquidez) {
        return false
      }

      // Filtro de pools ativas (assumindo que pools com reservas > 0 são ativas)
      if (filters.activeOnly && (pool.reserve0_amount <= 0 || pool.reserve1_amount <= 0)) {
        return false
      }

      return true
    })

    // Aplicar ordenação
    filtered.sort((a, b) => {
      const field = filters.sortBy
      const order = filters.sortOrder === "desc" ? -1 : 1

      let valA: any
      let valB: any

      if (field === "liquidity") {
        valA = a.liquidity
        valB = b.liquidity
      } else if (field === "volume") {
        valA = a.volume24h
        valB = b.volume24h
      } else if (field === "price") {
        valA = a.price
        valB = b.price
      } else if (field === "pair") {
        valA = a.pair
        valB = b.pair
      } else {
        return 0 // No valid sort field
      }

      if (typeof valA === "string" && typeof valB === "string") {
        return valA.localeCompare(valB) * order
      }
      return (valA - valB) * order
    })

    return filtered
  }, [cachedData, filters])

  const sortedPools = useMemo(() => {
    return getFilteredPoolData
  }, [getFilteredPoolData])

  // --- Funcionalidade de Export ---
  const exportFilteredData = useCallback(() => {
    const dataToExport = getFilteredPoolData
    const dataStr = JSON.stringify(
      {
        exported_at: new Date().toISOString(),
        filters_applied: filters,
        total_pools: dataToExport.length,
        data: dataToExport,
      },
      null,
      2,
    )

    const dataBlob = new Blob([dataStr], { type: "application/json" })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement("a")
    link.href = url
    link.download = `wax_pools_filtered_${new Date().toISOString().split("T")[0]}.json`
    document.body.appendChild(link) // Required for Firefox
    link.click()
    document.body.removeChild(link) // Clean up
    URL.revokeObjectURL(url) // Free up memory
  }, [getFilteredPoolData, filters])

  // --- Renderização da Interface ---
  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-4 md:p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl font-extrabold text-center text-blue-400 mb-8">WAX DEX Pools Monitor</h1>

        {/* Painel de Controle */}
        <Card className="mb-6 bg-gray-800 border-gray-700 text-white">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xl font-bold">Controle de Dados</CardTitle>
            <Button
              onClick={updateAllPoolData}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md transition-colors duration-200"
              disabled={loading}
            >
              {loading ? "Atualizando..." : "🔄 Atualizar Todos os Dados"}
            </Button>
          </CardHeader>
          <CardContent>
            {error && <p className="text-red-500 mb-4">{error}</p>}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {CONTRACTS_TO_MONITOR.map((contract) => (
                <Card
                  key={contract.id}
                  className={`p-3 rounded-lg ${
                    cachedData[contract.id] === null ? "bg-red-800 border-red-600" : "bg-gray-700 border-gray-600"
                  }`}
                >
                  <h3 className="font-semibold text-lg text-blue-300">{contract.name}</h3>
                  <p className="text-sm text-gray-300">
                    {cachedData[contract.id] === null
                      ? "Falha ao carregar"
                      : cachedData[contract.id]
                        ? `${cachedData[contract.id]?.total_rows} pools cached`
                        : "Não carregado"}
                  </p>
                  <p className="text-xs text-gray-400">
                    {lastUpdate[contract.id]
                      ? `Atualizado: ${new Date(lastUpdate[contract.id]!).toLocaleString()}`
                      : "Nunca atualizado"}
                  </p>
                </Card>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Painel de Filtros */}
        <Card className="mb-6 bg-gray-800 border-gray-700 text-white">
          <CardHeader>
            <CardTitle className="text-lg font-bold">Filtros</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Filtro por Contrato */}
              <div>
                <Label htmlFor="contract-filter" className="mb-1 block text-gray-300">
                  Contrato
                </Label>
                <Select
                  value={filters.contract}
                  onValueChange={(value) => setFilters((prev) => ({ ...prev, contract: value }))}
                >
                  <SelectTrigger id="contract-filter" className="bg-gray-700 border-gray-600 text-white">
                    <SelectValue placeholder="Selecione um contrato" />
                  </SelectTrigger>
                  <SelectContent className="bg-gray-700 text-white border-gray-600">
                    <SelectItem value="all">Todos os Contratos</SelectItem>
                    {CONTRACTS_TO_MONITOR.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Busca por Token */}
              <div>
                <Label htmlFor="token-search" className="mb-1 block text-gray-300">
                  Buscar Token
                </Label>
                <Input
                  id="token-search"
                  type="text"
                  placeholder="Ex: WAX, TACO, USDT"
                  value={filters.tokenSearch}
                  onChange={(e) => setFilters((prev) => ({ ...prev, tokenSearch: e.target.value }))}
                  className="bg-gray-700 border-gray-600 text-white placeholder-gray-400"
                />
              </div>

              {/* Liquidez Mínima */}
              <div>
                <Label htmlFor="min-liquidity" className="mb-1 block text-gray-300">
                  Liquidez Mínima
                </Label>
                <Input
                  id="min-liquidity"
                  type="number"
                  placeholder="0"
                  value={filters.minLiquidity}
                  onChange={(e) => setFilters((prev) => ({ ...prev, minLiquidity: Number(e.target.value) }))}
                  className="bg-gray-700 border-gray-600 text-white"
                />
              </div>

              {/* Ordenação */}
              <div>
                <Label htmlFor="sort-by" className="mb-1 block text-gray-300">
                  Ordenar por
                </Label>
                <Select
                  value={`${filters.sortBy}-${filters.sortOrder}`}
                  onValueChange={(value) => {
                    const [sortBy, sortOrder] = value.split("-")
                    setFilters((prev) => ({
                      ...prev,
                      sortBy: sortBy as Filters["sortBy"],
                      sortOrder: sortOrder as Filters["sortOrder"],
                    }))
                  }}
                >
                  <SelectTrigger id="sort-by" className="bg-gray-700 border-gray-600 text-white">
                    <SelectValue placeholder="Selecione a ordenação" />
                  </SelectTrigger>
                  <SelectContent className="bg-gray-700 text-white border-gray-600">
                    <SelectItem value="liquidity-desc">Maior Liquidez</SelectItem>
                    <SelectItem value="liquidity-asc">Menor Liquidez</SelectItem>
                    <SelectItem value="price-desc">Maior Preço</SelectItem>
                    <SelectItem value="price-asc">Menor Preço</SelectItem>
                    <SelectItem value="pair-asc">Par (A-Z)</SelectItem>
                    <SelectItem value="pair-desc">Par (Z-A)</SelectItem>
                    <SelectItem value="volume-desc">Maior Volume (Placeholder)</SelectItem>
                    <SelectItem value="volume-asc">Menor Volume (Placeholder)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Ativo Apenas */}
              <div className="flex items-center space-x-2 col-span-full md:col-span-1">
                <Switch
                  id="active-only"
                  checked={filters.activeOnly}
                  onCheckedChange={(checked) => setFilters((prev) => ({ ...prev, activeOnly: checked }))}
                  className="data-[state=checked]:bg-blue-600"
                />
                <Label htmlFor="active-only" className="text-gray-300">
                  Mostrar apenas pools ativas (reservas &gt; 0)
                </Label>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Botão de Exportar */}
        <div className="flex justify-end mb-4">
          <Button
            onClick={exportFilteredData}
            className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-md transition-colors duration-200 flex items-center gap-2"
          >
            <Download className="h-4 w-4" /> Exportar Dados Filtrados (.json)
          </Button>
        </div>

        {/* Tabela de Dados */}
        <Card className="bg-gray-800 border-gray-700">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left table-auto">
                <thead className="bg-gray-700">
                  <tr>
                    <th className="px-4 py-3 text-blue-300 font-semibold text-sm uppercase tracking-wider">Par</th>
                    <th className="px-4 py-3 text-blue-300 font-semibold text-sm uppercase tracking-wider">DEX</th>
                    <th className="px-4 py-3 text-blue-300 font-semibold text-sm uppercase tracking-wider">
                      Contrato Token A
                    </th>
                    <th className="px-4 py-3 text-blue-300 font-semibold text-sm uppercase tracking-wider">
                      Contrato Token B
                    </th>
                    <th className="px-4 py-3 text-blue-300 font-semibold text-sm uppercase tracking-wider">Liquidez</th>
                    <th className="px-4 py-3 text-blue-300 font-semibold text-sm uppercase tracking-wider">
                      Preço (TokenB/TokenA)
                    </th>
                    <th className="px-4 py-3 text-blue-300 font-semibold text-sm uppercase tracking-wider">
                      Volume 24h (Placeholder)
                    </th>
                    <th className="px-4 py-3 text-blue-300 font-semibold text-sm uppercase tracking-wider">
                      Última Atualização
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPools.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="text-center py-8 text-gray-400">
                        {loading ? "Carregando dados..." : "Nenhum dado encontrado com os filtros aplicados."}
                      </td>
                    </tr>
                  ) : (
                    sortedPools.map((pool) => (
                      <tr
                        key={`${pool.contract}-${pool.id}`}
                        className="border-b border-gray-700 hover:bg-gray-700 transition-colors duration-150"
                      >
                        <td className="px-4 py-3 font-medium text-white">{pool.pair}</td>
                        <td className="px-4 py-3 text-gray-300">
                          {CONTRACTS_TO_MONITOR.find((c) => c.id === pool.contract)?.name || pool.contract}
                        </td>
                        <td className="px-4 py-3 text-gray-300 text-xs">{pool.token0_contract}</td>
                        <td className="px-4 py-3 text-gray-300 text-xs">{pool.token1_contract}</td>
                        <td className="px-4 py-3 text-gray-300">{pool.liquidity.toFixed(2)}</td>
                        <td className="px-4 py-3 text-green-400">{pool.price.toFixed(8)}</td>
                        <td className="px-4 py-3 text-gray-300">{pool.volume24h.toFixed(2)}</td>
                        <td className="px-4 py-3 text-gray-400">{new Date(pool.last_update).toLocaleString()}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export default PoolMonitor
