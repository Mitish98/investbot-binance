import streamlit as st
import asyncio
from binance.client import Client
import pandas as pd
import requests
import time
import datetime
from ta.momentum import RSIIndicator
from dotenv import load_dotenv
import os

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Importando credenciais
api_key_spot = os.getenv("api_key_spot")
api_secret_spot = os.getenv("api_secret_spot")

# Verifique se as credenciais foram carregadas corretamente
if not api_key_spot or not api_secret_spot:
    st.error("As credenciais da API não foram carregadas corretamente. Verifique o arquivo .env.")

# Inicializando o cliente Binance
client = Client(api_key_spot, api_secret_spot)

# Funções auxiliares
def sync_time():
    try:
        url = 'https://fapi.binance.com/fapi/v1/time'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        server_time = response.json()['serverTime']
        local_time = int(time.time() * 1000)
        time_difference = server_time - local_time
        return time_difference
    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao sincronizar o tempo: {e}")
        return 0

def calculate_bollinger_bands(df, num_periods=21, std_dev_factor=2):
    df['SMA'] = df['close'].rolling(window=num_periods).mean()
    df['std_dev'] = df['close'].rolling(window=num_periods).std()
    df['upper_band'] = df['SMA'] + (std_dev_factor * df['std_dev'])
    df['lower_band'] = df['SMA'] - (std_dev_factor * df['std_dev'])
    return df

def calculate_stochastic_oscillator(df, k_period=14, d_period=3):
    df['L14'] = df['low'].rolling(window=k_period).min()
    df['H14'] = df['high'].rolling(window=k_period).max()
    df['%K'] = ((df['close'] - df['L14']) / (df['H14'] - df['L14'])) * 100
    df['%D'] = df['%K'].rolling(window=d_period).mean()
    return df

# Sincronizando tempo
time_difference = sync_time()

async def fetch_ticker_and_candles(symbol, timeframe):
    try:
        ticker = client.futures_ticker(symbol=symbol)
        bars = client.futures_klines(symbol=symbol, interval=timeframe, limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
                                         'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 
                                         'taker_buy_quote_asset_volume', 'ignore'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        current_price = float(ticker['lastPrice'])
        return current_price, df
    except Exception as e:
        st.error(f"Erro ao buscar dados para {symbol}: {e}")
        return None, None

async def notify_conditions(symbol, timeframes):
    """Envia notificações continuamente com base nas condições técnicas para múltiplos timeframes."""
    while True:  # Loop infinito
        for timeframe in timeframes:
            current_price, df = await fetch_ticker_and_candles(symbol, timeframe)
            if df is None:
                await asyncio.sleep(5)  # Espera 5 segundos antes de tentar novamente
                continue

            # Indicadores
            df = calculate_bollinger_bands(df)
            df = calculate_stochastic_oscillator(df)
            rsi_indicator = RSIIndicator(df['close'], window=14)
            df['rsi'] = rsi_indicator.rsi()

            upper_band = df['upper_band'].iloc[-1]
            lower_band = df['lower_band'].iloc[-1]
            stochastic_k = df['%K'].iloc[-1]
            stochastic_d = df['%D'].iloc[-1]
            rsi = df['rsi'].iloc[-1]
            volume_ma = df['volume'].rolling(window=21).mean().iloc[-1]

            # Condições de compra
            if current_price < lower_band and stochastic_k < 20 and stochastic_d < 20 and df['volume'].iloc[-1] > volume_ma and rsi < 30:
                st.info(f"[{datetime.datetime.now()}] Sinal de COMPRA para {symbol} no timeframe {timeframe}: Preço atual: {current_price}")

            # Condições de venda
            if current_price > upper_band and stochastic_k > 80 and stochastic_d > 80 and df['volume'].iloc[-1] > volume_ma and rsi > 70:
                st.info(f"[{datetime.datetime.now()}] Sinal de VENDA para {symbol} no timeframe {timeframe}: Preço atual: {current_price}")

            await asyncio.sleep(60)  # Aguarda 60 segundos antes de verificar novamente

# Configuração do Streamlit
st.title("Robô de Notificação para Criptomoedas")
st.write("O sistema utiliza uma combinação de indicadores técnicos para gerar sinais de compra e venda para os pares de moedas selecionados ao identificar oportunidades de mercado baseadas em condições extremas de preço e volume.")
st.write("As condições de compra são acionadas quando o preço atual está abaixo da Banda Inferior de Bollinger, o Estocástico está abaixo de 20, o volume de negociações está acima da média móvel e o RSI (Índice de Força Relativa) está abaixo de 30, indicando uma possível sobrevenda. Por outro lado, as condições de venda são ativadas quando o preço supera a Banda Superior de Bollinger, o Estocástico está acima de 80, o volume é maior que a média e o RSI ultrapassa 70, sugerindo uma possível sobrecompra.")
st.write("Escolha as criptomoedas que deseja receber notificação, selecione o(s) seu(s) timeframe(s) de análise e clique em 'Iniciar Monitoramento'")
st.sidebar.header("Configurações")

# Entrada do usuário
symbols = st.sidebar.multiselect("Selecione os pares de moedas", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "DOTUSDT", "DOGEUSDT", "FTMUSDT", "ASTRUSDT", "XRPUSDT", "SOLUSDT", "LTCUSDT","PENDLEUSDT", "1000PEPEUSDT", "1000SHIBUSDT","AAVEUSDT","ORDIUSDT","UNIUSDT","LINKUSDT","ENSUSDT", "MOVRUSDT","ARBUSDT","TRBUSDT","MANTAUSDT","AVAXUSDT","NEIROUSDT", "1000BONKUSDT", "1000FLOKIUSDT"])
timeframes = st.sidebar.multiselect("Selecione o(s) timeframe(s)", ["1m", "5m", "15m", "1h", "4h", "1d"])

if st.sidebar.button("Iniciar Monitoramento"):
    try:
        if not symbols:
            st.error("Por favor, selecione pelo menos um par de moedas.")
        if not timeframes:
            st.error("Por favor, selecione pelo menos um timeframe.")
        else:
            st.success("Monitoramento iniciado! Acompanhe os alertas abaixo.")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            tasks = [notify_conditions(symbol, timeframes) for symbol in symbols]
            loop.run_until_complete(asyncio.gather(*tasks))
    except Exception as e:
        st.error(f"Erro ao iniciar o monitoramento: {e}")
