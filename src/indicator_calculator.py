"""
Módulo 3: Cálculo de indicadores técnicos
Calcula HMA16, EMAs, tendencias, VMA20 y patrones de velas.
Genera archivos *_indicators.csv en data_indicators/
"""

import pandas as pd
import numpy as np
from pathlib import Path


def wma(series, window):
    """
    Calcula Weighted Moving Average (WMA) con pesos lineales:
    window, window-1, ..., 1
    """
    weights = np.arange(1, window + 1)
    return series.rolling(window).apply(
        lambda x: np.dot(x, weights) / weights.sum(),
        raw=True
    )


def calculate_hma(close_series, span=16):
    """
    Calcula Hull Moving Average (HMA) con WMA real:
      1) WMA(span/2)
      2) WMA(span)
      3) Diff = 2 * WMA(span/2) - WMA(span)
      4) HMA = WMA(Diff, sqrt(span))
    Ejemplo para HMA16:
      WMA8, WMA16, Diff, WMA4(Diff)
    """
    half_span = span // 2          # 8 para 16
    sqrt_span = int(np.sqrt(span)) # 4 para 16

    wma_half = wma(close_series, half_span)
    wma_full = wma(close_series, span)
    diff = 2 * wma_half - wma_full
    hma = wma(diff, sqrt_span)

    return hma.round(2)


def calculate_hma_trend(hma_series):
    """
    Calcula etiqueta de tendencia HMA con cuatro estados:
    - Bajista: fase de caída ya establecida
    - Venta: primeras ruedas de giro de Alcista a Bajista
    - Compra: primeras ruedas de giro de Bajista a Alcista
    - Alcista: fase de suba ya establecida
    """
    trend = []
    prev_slope = None
    up_turn_count = 0
    down_turn_count = 0

    # Primera fila: inicializamos como Bajista
    trend.append('Bajista')
    prev_slope = None

    for i in range(1, len(hma_series)):
        cur = hma_series.iloc[i]
        prev = hma_series.iloc[i - 1]

        # Si falta dato, volvemos a Bajista por defecto
        if pd.isna(cur) or pd.isna(prev):
            trend.append('Bajista')
            prev_slope = None
            up_turn_count = 0
            down_turn_count = 0
            continue

        # Determinar pendiente actual
        if cur > prev:
            slope = 'up'
        elif cur < prev:
            slope = 'down'
        else:
            slope = prev_slope

        if prev_slope is None:
            if slope == 'up':
                trend.append('Compra')
                up_turn_count = 1
                down_turn_count = 0
            elif slope == 'down':
                trend.append('Bajista')
                up_turn_count = 0
                down_turn_count = 0
            else:
                trend.append('Bajista')
        else:
            # Giro de Bajista/neutral a subida → Compra
            if slope == 'up' and prev_slope != 'up':
                up_turn_count = 1
                down_turn_count = 0
                trend.append('Compra')
            # Giro de Alcista/neutral a bajada → Venta
            elif slope == 'down' and prev_slope != 'down':
                down_turn_count = 1
                up_turn_count = 0
                trend.append('Venta')
            else:
                if slope == 'up':
                    if 0 < up_turn_count < 2:
                        up_turn_count += 1
                        trend.append('Compra')
                    else:
                        trend.append('Alcista')
                    down_turn_count = 0
                elif slope == 'down':
                    if 0 < down_turn_count < 2:
                        down_turn_count += 1
                        trend.append('Venta')
                    else:
                        trend.append('Bajista')
                    up_turn_count = 0
                else:
                    trend.append(trend[-1])

        prev_slope = slope

    return trend


def calculate_ema_crossover_trend_12_26(ema12_series, ema26_series):
    """
    Tendencia basada en cruce EMA12/EMA26:
    - Bajista: EMA12 < EMA26, fase establecida
    - Venta: primeras ruedas de cruce de arriba hacia abajo
    - Compra: primeras ruedas de cruce de abajo hacia arriba
    - Alcista: EMA12 > EMA26, fase establecida
    """
    trend = []
    prev_position = None  # 'above' o 'below'
    up_turn_count = 0
    down_turn_count = 0

    # Primera fila
    trend.append('Bajista')

    for i in range(1, len(ema12_series)):
        ema12 = ema12_series.iloc[i]
        ema26 = ema26_series.iloc[i]

        if pd.isna(ema12) or pd.isna(ema26):
            trend.append('Bajista')
            prev_position = None
            up_turn_count = 0
            down_turn_count = 0
            continue

        if ema12 > ema26:
            position = 'above'
        elif ema12 < ema26:
            position = 'below'
        else:
            position = prev_position

        if prev_position is None:
            if position == 'above':
                trend.append('Compra')
                up_turn_count = 1
                down_turn_count = 0
            elif position == 'below':
                trend.append('Bajista')
                up_turn_count = 0
                down_turn_count = 0
            else:
                trend.append('Bajista')
        else:
            if position == 'above' and prev_position != 'above':
                up_turn_count = 1
                down_turn_count = 0
                trend.append('Compra')
            elif position == 'below' and prev_position != 'below':
                down_turn_count = 1
                up_turn_count = 0
                trend.append('Venta')
            else:
                if position == 'above':
                    if 0 < up_turn_count < 2:
                        up_turn_count += 1
                        trend.append('Compra')
                    else:
                        trend.append('Alcista')
                    down_turn_count = 0
                elif position == 'below':
                    if 0 < down_turn_count < 2:
                        down_turn_count += 1
                        trend.append('Venta')
                    else:
                        trend.append('Bajista')
                    up_turn_count = 0
                else:
                    trend.append(trend[-1])

        prev_position = position

    return trend


def calculate_ema_crossover_trend_10_50_100(ema10_series, ema50_series):
    """
    Tendencia basada en cruce EMA10/EMA50:
    - Bajista: EMA10 < EMA50, fase establecida
    - Venta: primeras ruedas de cruce de arriba hacia abajo
    - Compra: primeras ruedas de cruce de abajo hacia arriba
    - Alcista: EMA10 > EMA50, fase establecida
    
    EMA100 se calcula pero no interviene en la lógica de estado.
    """
    trend = []
    prev_position = None  # 'above' o 'below'
    up_turn_count = 0
    down_turn_count = 0

    # Primera fila
    trend.append('Bajista')

    for i in range(1, len(ema10_series)):
        ema10 = ema10_series.iloc[i]
        ema50 = ema50_series.iloc[i]

        if pd.isna(ema10) or pd.isna(ema50):
            trend.append('Bajista')
            prev_position = None
            up_turn_count = 0
            down_turn_count = 0
            continue

        if ema10 > ema50:
            position = 'above'
        elif ema10 < ema50:
            position = 'below'
        else:
            position = prev_position

        if prev_position is None:
            if position == 'above':
                trend.append('Compra')
                up_turn_count = 1
                down_turn_count = 0
            elif position == 'below':
                trend.append('Bajista')
                up_turn_count = 0
                down_turn_count = 0
            else:
                trend.append('Bajista')
        else:
            if position == 'above' and prev_position != 'above':
                up_turn_count = 1
                down_turn_count = 0
                trend.append('Compra')
            elif position == 'below' and prev_position != 'below':
                down_turn_count = 1
                up_turn_count = 0
                trend.append('Venta')
            else:
                if position == 'above':
                    if 0 < up_turn_count < 2:
                        up_turn_count += 1
                        trend.append('Compra')
                    else:
                        trend.append('Alcista')
                    down_turn_count = 0
                elif position == 'below':
                    if 0 < down_turn_count < 2:
                        down_turn_count += 1
                        trend.append('Venta')
                    else:
                        trend.append('Bajista')
                    up_turn_count = 0
                else:
                    trend.append(trend[-1])

        prev_position = position

    return trend


def calculate_vma20(df):
    """
    Calcula VMA20 como volumen relativo:
    vma20 = volume / promedio_20_dias(volume)
    Siempre positivo, redondeado a 2 decimales.
    """
    vol_ma20 = df['volume'].rolling(window=20).mean()
    vma20 = df['volume'] / vol_ma20
    return vma20.round(2)


def categorize_vma20(vma20_series):
    """
    Categoriza VMA20:
    Muy Bajo: vma20 < 0.7
    Bajo:     0.7 <= vma20 < 0.9
    Medio:    0.9 <= vma20 < 1.3
    Alto:     1.3 <= vma20 < 2.0
    Muy Alto: vma20 >= 2.0
    """
    conditions = [
        vma20_series < 0.7,
        (vma20_series >= 0.7) & (vma20_series < 0.9),
        (vma20_series >= 0.9) & (vma20_series < 1.3),
        (vma20_series >= 1.3) & (vma20_series < 2.0),
        vma20_series >= 2.0
    ]
    choices = ['Muy Bajo', 'Bajo', 'Medio', 'Alto', 'Muy Alto']
    return np.select(conditions, choices, default='Medio')


def identify_candle_pattern(df):
    """
    Identifica patrones de velas:
    
    Patrones de una vela:
    - Doji: cuerpo muy pequeño relativo al rango (body_pct < 0.1)
    - Marubozu_Alc: cuerpo grande alcista sin sombras (body_pct > 0.8, close > open)
    - Marubozu_Baj: cuerpo grande bajista sin sombras (body_pct > 0.8, close < open)
    
    Patrones de dos velas:
    - Engulfing_Alc: cuerpo alcista actual envuelve completamente el cuerpo bajista anterior
    - Engulfing_Baj: cuerpo bajista actual envuelve completamente el cuerpo alcista anterior
    
    Prioridad: Engulfing > patrones de una vela > ''
    """
    body = (df['close'] - df['open']).values
    range_val = (df['high'] - df['low']).values
    
    body_pct = np.where(range_val > 0, np.abs(body) / range_val, 0)
    
    upper_shadow = (df['high'] - df[['open', 'close']].max(axis=1)).values
    lower_shadow = (df[['open', 'close']].min(axis=1) - df['low']).values
    
    open_vals = df['open'].values
    close_vals = df['close'].values
    
    patterns = []
    
    for i in range(len(df)):
        pattern = ''
        
        # Primero verificar patrones de dos velas (Engulfing)
        if i > 0:
            # Datos de hoy
            open_today = open_vals[i]
            close_today = close_vals[i]
            body_today = body[i]
            
            # Datos de ayer
            open_yesterday = open_vals[i - 1]
            close_yesterday = close_vals[i - 1]
            body_yesterday = body[i - 1]
            
            # Engulfing Alcista:
            # - Ayer bajista (close < open)
            # - Hoy alcista (close > open)
            # - Cuerpo de hoy envuelve completamente el cuerpo de ayer
            if (body_yesterday < 0 and body_today > 0 and
                close_today > open_yesterday and
                open_today < close_yesterday):
                pattern = 'Engulfing_Alc'
            
            # Engulfing Bajista:
            # - Ayer alcista (close > open)
            # - Hoy bajista (close < open)
            # - Cuerpo de hoy envuelve completamente el cuerpo de ayer
            elif (body_yesterday > 0 and body_today < 0 and
                  open_today > close_yesterday and
                  close_today < open_yesterday):
                pattern = 'Engulfing_Baj'
        
        # Si no hay Engulfing, verificar patrones de una vela
        if pattern == '':
            r = range_val[i]
            bp = body_pct[i]
            b = body[i]
            us = upper_shadow[i]
            ls = lower_shadow[i]
            
            # Doji
            if bp < 0.1 and r > 0:
                pattern = 'Doji'
            # Marubozu Alcista
            elif bp > 0.8 and b > 0 and us < 0.1 * r and ls < 0.1 * r:
                pattern = 'Marubozu_Alc'
            # Marubozu Bajista
            elif bp > 0.8 and b < 0 and us < 0.1 * r and ls < 0.1 * r:
                pattern = 'Marubozu_Baj'
        
        patterns.append(pattern)
    
    return patterns


def calculate_candle_signal(candle_pattern_series):
    """
    Señal de velas con prioridad:

    1. Si hoy hay patrón:
       - Engulfing_Alc  → Alcista
       - Engulfing_Baj  → Bajista
       - Doji           → Indeterminacion
       - Marubozu_Alc   → Alcista
       - Marubozu_Baj   → Bajista
       En este caso no se mira hacia atrás.

    2. Si hoy no hay patrón (''), buscar hasta 3 ruedas hacia atrás:
       - Engulfing_Alc o Marubozu_Alc → "Alcista X rueda(s) atras"
       - Engulfing_Baj o Marubozu_Baj → "Bajista X rueda(s) atras"

    3. Si no se encuentra nada en las últimas 3 ruedas → Neutra.
    """
    signals = []

    for i in range(len(candle_pattern_series)):
        pattern_today = candle_pattern_series.iloc[i]

        # 1) Hoy hay patrón → señal directa
        if pattern_today == 'Engulfing_Alc':
            signals.append('Alcista')
            continue
        elif pattern_today == 'Engulfing_Baj':
            signals.append('Bajista')
            continue
        elif pattern_today == 'Doji':
            signals.append('Indeterminacion')
            continue
        elif pattern_today == 'Marubozu_Alc':
            signals.append('Alcista')
            continue
        elif pattern_today == 'Marubozu_Baj':
            signals.append('Bajista')
            continue

        # 2) Hoy no hay patrón → buscar hacia atrás
        found = False
        for lookback in range(1, 4):
            if i - lookback < 0:
                break
            pattern_past = candle_pattern_series.iloc[i - lookback]

            # Alcistas que se propagan como contexto
            if pattern_past in ('Engulfing_Alc', 'Marubozu_Alc'):
                signals.append(f'Alcista {lookback} rueda{"s" if lookback > 1 else ""} atras')
                found = True
                break

            # Bajistas que se propagan como contexto
            if pattern_past in ('Engulfing_Baj', 'Marubozu_Baj'):
                signals.append(f'Bajista {lookback} rueda{"s" if lookback > 1 else ""} atras')
                found = True
                break

        # 3) Sin nada relevante en 3 ruedas → Neutra
        if not found:
            signals.append('Neutra')

    return signals


def process_ticker(ticker, input_dir, output_dir):
    """
    Procesa un ticker: lee CSV normalizado, calcula indicadores, guarda resultado.
    """
    input_file = input_dir / f"{ticker}_normalized.csv"
    if not input_file.exists():
        print(f"  ⚠️  Archivo no encontrado: {input_file}")
        return
    
    df = pd.read_csv(input_file)
    required_cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'ticker']
    if not all(col in df.columns for col in required_cols):
        print(f"  ⚠️  Faltan columnas requeridas en {input_file}")
        return
    
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    # HMA16 + tendencia
    df['hma16'] = calculate_hma(df['close'], span=16)
    df['T_hma16'] = calculate_hma_trend(df['hma16'])
    
    # EMAs con ventana mínima
    for span in [10, 12, 26, 50, 100]:
        ema = df['close'].ewm(span=span, adjust=False).mean()
        ema.iloc[:span-1] = np.nan
        df[f'ema{span}'] = ema.round(2)
    
    # Tendencias por cruces EMAs
    df['T_ema12_26'] = calculate_ema_crossover_trend_12_26(df['ema12'], df['ema26'])
    df['T_ema10_50_100'] = calculate_ema_crossover_trend_10_50_100(df['ema10'], df['ema50'])
    
    # VMA20
    df['vma20'] = calculate_vma20(df)
    df['vma20_cat'] = categorize_vma20(df['vma20'])
    
    # Velas (ahora incluye Engulfing)
    df['candle_pattern'] = identify_candle_pattern(df)
    df['candle_signal'] = calculate_candle_signal(df['candle_pattern'])
    
    # Orden de columnas solicitado
    output_cols = [
        'date', 'open', 'high', 'low', 'close', 'volume', 'ticker',
        'vma20', 'vma20_cat',
        'ema10', 'ema12', 'ema26', 'ema50', 'ema100',
        'hma16',
        'T_ema12_26', 'T_ema10_50_100', 'T_hma16',
        'candle_pattern', 'candle_signal'
    ]
    df_output = df[output_cols].copy()
    df_output['date'] = df_output['date'].dt.strftime('%Y-%m-%d')
    
    output_file = output_dir / f"{ticker}_indicators.csv"
    df_output.to_csv(output_file, index=False)
    print(f"  ✓ {ticker}: {len(df_output)} filas → {output_file.name}")


def main():
    base_dir = Path.cwd()
    input_dir = base_dir / 'data_normalized'
    output_dir = base_dir / 'data_indicators'
    output_dir.mkdir(exist_ok=True)
    
    print("=" * 60)
    print("MÓDULO 3: Cálculo de indicadores técnicos")
    print("=" * 60)
    print(f"Entrada:  {input_dir}")
    print(f"Salida:   {output_dir}\n")
    
    normalized_files = list(input_dir.glob('*_normalized.csv'))
    if not normalized_files:
        print("⚠️  No se encontraron archivos *_normalized.csv")
        return
    
    print(f"Archivos encontrados: {len(normalized_files)}\n")
    
    for file in normalized_files:
        ticker = file.stem.replace('_normalized', '')
        process_ticker(ticker, input_dir, output_dir)
    
    print("\n" + "=" * 60)
    print("✓ Módulo 3 completado")
    print("=" * 60)


if __name__ == '__main__':
    main()