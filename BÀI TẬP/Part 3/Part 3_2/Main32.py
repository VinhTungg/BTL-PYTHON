# -*- coding: utf-8 -*-
import sqlite3
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score
import warnings
warnings.filterwarnings('ignore')

DB_PATH = "../fbref_pl_2024_2025_full.sqlite"
TABLE_STATS = "player_stats_cleaned"
TABLE_VALS = "player_transfer_values_2024_2025"

def parse_value(val):
    if pd.isna(val) or val == "N/a":
        return np.nan
    s = str(val).lower().strip().replace("€", "").replace(",", "")
    try:
        if "m" in s:
            return float(s.replace("m", "").strip())
        if "k" in s:
            return float(s.replace("k", "").strip()) / 1000.0
        return float(s)
    except:
        return np.nan

def load_data():
    with sqlite3.connect(DB_PATH) as conn:
        stats = pd.read_sql(f"SELECT * FROM {TABLE_STATS}", conn)
        vals = pd.read_sql(f"SELECT * FROM {TABLE_VALS}", conn)

    stats["player_clean"] = stats["player"].astype(str).str.lower().str.strip()
    vals["player_clean"] = vals["player"].astype(str).str.lower().str.strip()
    vals["market_value"] = vals["market_value"].apply(parse_value)

    df = stats.merge(vals[["player_clean", "market_value"]], on="player_clean", how="left")
    return df

def clean_numeric_columns(df):
    df = df.copy()
    
    dt_cols = df.select_dtypes(include=['datetime64[ns]', 'datetime64[ns, UTC]']).columns.tolist()
    if dt_cols:
        df = df.drop(columns=dt_cols)

    numeric_like_cols = ['age', 'minutes', 'goals', 'assists', 'xg', 'xg_assist', 'npxg']

    for col in numeric_like_cols:
        if col not in df.columns:
            continue
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(",", "")
            .str.replace("€", "")
            .str.replace("%", "")
            .str.strip()
        )
        df[col] = pd.to_numeric(df[col], errors='coerce')

    return df

def create_smart_features(df):
    df_fe = df.copy()
    
    def simple_position(pos):
        if pd.isna(pos):
            return "Other"
        pos = str(pos).upper()
        if 'GK' in pos: return "Goalkeeper"
        elif any(p in pos for p in ['CB', 'CENTRE-BACK']): return "Centre-Back"
        elif any(p in pos for p in ['RB', 'LB', 'FULL-BACK']): return "Full-Back"
        elif any(p in pos for p in ['DM', 'DEFENSIVE MID']): return "Defensive Midfielder"
        elif any(p in pos for p in ['CM', 'CENTRAL MID']): return "Central Midfielder"
        elif any(p in pos for p in ['AM', 'ATTACKING MID']): return "Attacking Midfielder"
        elif any(p in pos for p in ['RW', 'LW', 'WINGER']): return "Winger"
        elif any(p in pos for p in ['FW', 'ST', 'FORWARD']): return "Forward"
        else: return "Other"
    
    df_fe['position_group'] = df_fe['position'].apply(simple_position)
    
    core_numeric = ['age', 'minutes', 'goals', 'assists', 'xg', 'xg_assist', 'npxg']
    
    for col in core_numeric:
        if col in df_fe.columns:
            df_fe[col] = pd.to_numeric(df_fe[col], errors="coerce").fillna(0)
    
    if 'minutes' in df_fe.columns:
        mask = df_fe['minutes'] > 270
        
        if 'goals' in df_fe.columns:
            df_fe['goals_p90'] = np.where(mask, (df_fe['goals'] / df_fe['minutes']) * 90, 0)
        
        if 'assists' in df_fe.columns:
            df_fe['assists_p90'] = np.where(mask, (df_fe['assists'] / df_fe['minutes']) * 90, 0)
        
        if 'xg' in df_fe.columns:
            df_fe['xg_p90'] = np.where(mask, (df_fe['xg'] / df_fe['minutes']) * 90, 0)
        
        if 'xg_assist' in df_fe.columns:
            df_fe['xg_assist_p90'] = np.where(mask, (df_fe['xg_assist'] / df_fe['minutes']) * 90, 0)
    
    if all(col in df_fe.columns for col in ['goals', 'assists']):
        df_fe['goal_contributions'] = df_fe['goals'] + df_fe['assists']
        if 'minutes' in df_fe.columns:
            df_fe['contributions_p90'] = np.where(
                df_fe['minutes'] > 270,
                (df_fe['goal_contributions'] / df_fe['minutes']) * 90,
                0
            )
    
    if all(col in df_fe.columns for col in ['goals', 'xg']):
        df_fe['finishing'] = np.where(df_fe['xg'] > 0, df_fe['goals'] / df_fe['xg'], 0)
        df_fe['finishing_bonus'] = np.where(
            df_fe['finishing'] > 1.2, 1,
            np.where(df_fe['finishing'] < 0.7, -1, 0)
        )
    
    if 'age' in df_fe.columns:
        df_fe['age_premium'] = np.where(df_fe['age'] <= 21, 1,
                                      np.where(df_fe['age'] <= 23, 0.5,
                                      np.where(df_fe['age'] <= 25, 0.25, 0)))
        
        df_fe['age_penalty'] = np.where(df_fe['age'] >= 30, 0.5,
                                      np.where(df_fe['age'] >= 28, 0.25, 0))
    
    if 'minutes' in df_fe.columns:
        df_fe['minutes_consistency'] = np.where(df_fe['minutes'] > 1500, 1,
                                              np.where(df_fe['minutes'] > 900, 0.5, 0))
    
    df_fe['position_multiplier'] = 1.0
    df_fe.loc[df_fe['position_group'].isin(['Forward', 'Attacking Midfielder', 'Winger']), 'position_multiplier'] = 1.2
    df_fe.loc[df_fe['position_group'] == 'Goalkeeper', 'position_multiplier'] = 0.7
    
    return df_fe

def train_single_robust_model(df):
    train_df = df[df["market_value"].notna() & (df["market_value"] > 0.1)].copy()
    
    selected_features = [
        'age', 'minutes', 
        'goals_p90', 'assists_p90', 'xg_p90', 'xg_assist_p90',
        'goal_contributions', 'contributions_p90',
        'finishing_bonus', 'age_premium', 'age_penalty', 
        'minutes_consistency', 'position_multiplier'
    ]
    
    available_features = [f for f in selected_features if f in train_df.columns]
    
    for col in available_features:
        train_df[col] = pd.to_numeric(train_df[col], errors="coerce")
        train_df[col] = train_df[col].fillna(train_df[col].median())
    
    Q1 = train_df["market_value"].quantile(0.10)
    Q3 = train_df["market_value"].quantile(0.90)
    train_df = train_df[(train_df["market_value"] >= Q1) | (train_df["market_value"] > 50)]
    
    X = train_df[available_features].astype(float)
    y = train_df["market_value"].astype(float)

    X_train, X_test, y_train_raw, y_test_raw = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    y_train = np.log1p(y_train_raw)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = LinearRegression()
    model.fit(X_train_s, y_train)
    
    y_pred_log = model.predict(X_test_s)
    y_pred = np.expm1(y_pred_log)

    mae = mean_absolute_error(y_test_raw, y_pred)
    r2 = r2_score(y_test_raw, y_pred)
    
    print(f"📊 SINGLE MODEL PERFORMANCE:")
    print(f"   MAE: €{mae*1_000_000:,.0f}")
    print(f"   R²:  {r2:.3f}")
    
    return model, scaler, available_features

def apply_superstar_correction(df_pred, df_feat):
    preds = df_pred.copy()
    
    minutes = df_feat.get('minutes', pd.Series(0, index=df_feat.index)).fillna(0)
    goals_p90 = df_feat.get('goals_p90', pd.Series(0, index=df_feat.index)).fillna(0)
    assists_p90 = df_feat.get('assists_p90', pd.Series(0, index=df_feat.index)).fillna(0)
    contrib_p90 = df_feat.get('contributions_p90', pd.Series(0, index=df_feat.index)).fillna(0)
    xg_p90 = df_feat.get('xg_p90', pd.Series(0, index=df_feat.index)).fillna(0)

    superstar = (
        (minutes > 1500) & (
            (contrib_p90 > 0.8) |
            (goals_p90 > 0.6) |
            (xg_p90 > 0.7)
        )
    )

    base_val = preds['pred_value_mil'].fillna(0)
    boost = np.ones(len(preds))

    mid_mask = superstar & (base_val.between(20, 80))
    boost[mid_mask] = 1.25

    high_mask = superstar & (base_val > 80)
    boost[high_mask] = 1.12

    very_low_min = minutes < 400
    low_min = (minutes >= 400) & (minutes < 900)

    boost[very_low_min] *= 0.35
    boost[low_min] *= 0.7

    preds['pred_value_mil'] = base_val * boost
    preds['pred_value_mil'] = np.clip(preds['pred_value_mil'], 0.2, 130)

    return preds

def main():
    print("🚀 SMART LINEAR REGRESSION WITH SUPERSTAR CORRECTION")
    
    df = load_data()
    print(f"📥 Loaded {len(df)} players")
    
    df = clean_numeric_columns(df)
    df_featured = create_smart_features(df)
    model, scaler, features = train_single_robust_model(df_featured)
    
    df_pred = df_featured.copy()
    
    for col in features:
        df_pred[col] = pd.to_numeric(df_pred[col], errors="coerce")
        df_pred[col] = df_pred[col].fillna(df_pred[col].median())
    
    X_all = df_pred[features].astype(float)
    pred_log_all = model.predict(scaler.transform(X_all))
    df_pred["pred_value_mil"] = np.expm1(pred_log_all)
    
    df_pred = apply_superstar_correction(df_pred, df_featured)
    df_pred["pred_value_mil"] = np.round(df_pred["pred_value_mil"], 2)
    
    output_cols = ["player", "club", "position", "market_value", "pred_value_mil"]
    existing_cols = [c for c in output_cols if c in df_pred.columns]
    df_pred[existing_cols].to_csv(
    "linear_predictions.csv",
    index=False,
    encoding="utf-8-sig",
    sep=";", 
    decimal="," 
)
    
    print(f"💾 Saved predictions for {len(df_pred)} players")

if __name__ == "__main__":
    main()