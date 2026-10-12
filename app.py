import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sklearn.manifold import MDS
import re
import zipfile
import io
import os

st.set_page_config(page_title="Narrative Star Map Dashboard (3D Plotly)", layout="wide")

st.title("✨ 食のナラティブ・インタラクティブ星図ビュワー (3D立体版)")
st.sidebar.header("データと表示設定")

uploaded_fixed = st.sidebar.file_uploader("ナラティブ/座標データ (Excel または CSV)", type=["xlsx", "xls", "csv"])
uploaded_demo = st.sidebar.file_uploader("イベント参加者データ (CSV)", type=["csv"])
uploaded_summary = st.sidebar.file_uploader("グループ概況文データ (CSV) ※任意", type=["csv"])

def load_excel_safe(uploaded_file):
    try:
        return pd.ExcelFile(uploaded_file)
    except Exception as e:
        if "stylesheet" in str(e).lower() or "invalid xml" in str(e).lower():
            uploaded_file.seek(0)
            safe_io = io.BytesIO()
            with zipfile.ZipFile(uploaded_file, 'r') as zin:
                with zipfile.ZipFile(safe_io, 'w') as zout:
                    for item in zin.infolist():
                        if item.filename == 'xl/styles.xml':
                            minimal_styles = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"></styleSheet>'
                            zout.writestr(item, minimal_styles)
                        else:
                            zout.writestr(item, zin.read(item.filename))
            safe_io.seek(0)
            return pd.ExcelFile(safe_io)
        raise e

if uploaded_fixed and uploaded_demo:
    try:
        if uploaded_fixed.name.endswith('.csv'):
            df_fixed = pd.read_csv(uploaded_fixed)
        else:
            xl = load_excel_safe(uploaded_fixed)
            target_sheet = next((s for s in xl.sheet_names if 'coordinate' in s.lower() or 'coord' in s.lower() or 'データ' in s or '座標' in s or 'sheet' in s.lower()), xl.sheet_names[0])
            df_fixed = pd.read_excel(xl, sheet_name=target_sheet)
            
        df_demo = pd.read_csv(uploaded_demo)
        
        summary_dict = {}
        if uploaded_summary:
            df_sum = pd.read_csv(uploaded_summary)
            if 'Group' in df_sum.columns and 'Summary' in df_sum.columns:
                summary_dict = pd.Series(df_sum['Summary'].values, index=df_sum['Group']).to_dict()
        
        cols_lower = [str(c).lower() for c in df_fixed.columns]
        has_precomputed_coords = any('x' in c for c in cols_lower) and any('y' in c for c in cols_lower)
        
        if has_precomputed_coords:
            x_col = [c for c in df_fixed.columns if 'x' in str(c).lower()][0]
            y_col = [c for c in df_fixed.columns if 'y' in str(c).lower()][0]
            no_col = [c for c in df_fixed.columns if 'no' in str(c).lower() or '番号' in str(c)][0]
            title_col = [c for c in df_fixed.columns if '見出し' in str(c) or 'title' in str(c).lower() or '名' in str(c)][0]
            
            df_coords = pd.DataFrame({
                'No': pd.to_numeric(df_fixed[no_col], errors='coerce'),
                '見出し': df_fixed[title_col],
                'X': pd.to_numeric(df_fixed[x_col], errors='coerce'),
                'Y': pd.to_numeric(df_fixed[y_col], errors='coerce')
            }).dropna(subset=['No'])
        else:
            val_cols = df_fixed.columns[2:12] if len(df_fixed.columns) >= 12 else df_fixed.columns[2:]
            X_data = df_fixed[val_cols].replace('評価不能', 3).apply(pd.to_numeric, errors='coerce').fillna(3)
            
            nmds = MDS(n_components=2, metric=False, random_state=42, normalized_stress='auto', max_iter=3000, eps=1e-9)
            coords = nmds.fit_transform(X_data)
            
            df_coords = pd.DataFrame({
                'No': pd.to_numeric(df_fixed.iloc[:, 0], errors='coerce'), 
                '見出し': df_fixed.iloc[:, 1], 
                'X': coords[:, 0], 
                'Y': coords[:, 1]
            }).dropna(subset=['No'])
            
        coords_dict = df_coords.set_index('No').to_dict('index')
        
        group_col = [c for c in df_demo.columns if 'group' in c.lower() or 'グループ' in c][0]
        part_col = [c for c in df_demo.columns if 'part' in c.lower() or '参加者' in c or 'id' in c.lower()][0]
        my_card_col = [c for c in df_demo.columns if 'my' in c.lower() or '選んだ' in c][0]
        interest_col = [c for c in df_demo.columns if 'interest' in c.lower() or '関心' in c][0]

        def clean_card_string(s):
            if pd.isna(s) or str(s).strip() in ['', 'なし']:
                return []
            cleaned = re.sub(r'[\[\]]', '', str(s))
            return [int(float(c.strip())) for c in cleaned.split(',') if c.strip().replace('.0','').isdigit()]

        # 関心（ハート）の集計
        interest_map = {}
        for _, row in df_demo.iterrows():
            interests = clean_card_string(row[interest_col])
            for c in interests:
                if c not in interest_map:
                    interest_map[c] = []
                interest_map[c].append(f"{row[group_col]} {row[part_col]}")
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("表示モードの選択")
        
        group_options = ["（グループを選択しない：星図のみ）"] + sorted(df_demo[group_col].unique().tolist())
        selected_group = st.sidebar.selectbox("表示する対象", group_options)
        
        show_solid = st.sidebar.checkbox("実線（自分の星座）を表示する", value=True)
        show_dotted = st.sidebar.checkbox("点線（他者への関心）を表示する", value=True)
        show_labels = st.sidebar.checkbox("カードのタイトル（星の名前）を表示する", value=True)
        show_hearts = st.sidebar.checkbox("他者からの関心(♥)を表示する", value=True)
        
        if selected_group != "（グループを選択しない：星図のみ）":
            summary_text = summary_dict.get(selected_group, "このグループの概況文ファイル（CSV）がアップロードされていないか、該当グループのデータがありません。")
            st.info(f"**【{selected_group} の特徴・概況】**\n\n{summary_text}")
        
        # --- Plotlyによる 3D インタラクティブ図の構築 ---
        fig = go.Figure()
        
        # 1. 背景の星（全ナラティブ：Z=0平面）
        hover_texts = [f"No.{int(row['No'])}: {row['見出し']}" for _, row in df_coords.iterrows()]
        fig.add_trace(go.Scatter3d(
            x=df_coords['X'],
            y=df_coords['Y'],
            z=np.zeros(len(df_coords)),
            mode='markers',
            marker=dict(size=3, color='#FFFFFF', opacity=0.3),
            text=hover_texts,
            hoverinfo='text',
            name='全ナラティブ',
            showlegend=False
        ))
        
        # 2. グループごとのプロット・線描画（3D空間）
        if selected_group != "（グループを選択しない：星図のみ）":
            group_data = df_demo[df_demo[group_col] == selected_group]
            colors = ['#FF0D0D', '#1E90FF', '#FFD700', '#00FF66', '#FF1493', '#00FFFF']
            
            related_card_nos = set()
            
            for idx, (_, row) in enumerate(group_data.iterrows()):
                color = colors[idx % len(colors)]
                p_id = row[part_col]
                my_cards = clean_card_string(row[my_card_col])
                interest_cards = clean_card_string(row[interest_col])
                
                if show_solid: related_card_nos.update(my_cards)
                if show_dotted: related_card_nos.update(interest_cards)
                
                my_x = [coords_dict[c]['X'] for c in my_cards if c in coords_dict]
                my_y = [coords_dict[c]['Y'] for c in my_cards if c in coords_dict]
                if not my_x: continue
                
                # 中心点（ひし形）
                cx, cy = np.mean(my_x), np.mean(my_y)
                num_cards = len(my_cards)
                z_offset = 0.002 if num_cards == 1 else 0.005 + (num_cards * 0.003) + ((idx % 3) * 0.002)
                
                # 参加者アイコン（中心点・ひし形）
                if show_solid or show_dotted:
                    fig.add_trace(go.Scatter3d(
                        x=[cx], y=[cy], z=[z_offset],
                        mode='markers',
                        marker=dict(size=8, color=color, symbol='diamond', line=dict(color='white', width=1.5)),
                        name=f"参加者: {p_id}",
                        hoverinfo='text',
                        hovertext=f"参加者 ID: {p_id} (グループ: {selected_group})"
                    ))
                
                # ★実線（自分の星座）：太さを「6」に大幅アップして存在感を強調
                if show_solid:
                    for x, y, c_no in zip(my_x, my_y, my_cards):
                        fig.add_trace(go.Scatter3d(
                            x=[cx, x], y=[cy, y], z=[z_offset, 0],
                            mode='lines',
                            line=dict(color=color, width=6.0),
                            opacity=0.9,
                            showlegend=False,
                            hoverinfo='none'
                        ))
                        c_title = coords_dict.get(c_no, {}).get('見出し', '')
                        fig.add_trace(go.Scatter3d(
                            x=[x], y=[y], z=[0],
                            mode='markers',
                            marker=dict(size=6, color=color, symbol='circle', line=dict(color='white', width=1)),
                            showlegend=False,
                            hoverinfo='text',
                            hovertext=f"[{p_id}の選択カード] No.{c_no} {c_title}"
                        ))
                
                # ★点線（他者への関心）：太さを「7」にさらに太くし、さらにダッシュ間隔を明確化するため等間隔のマーカー（ドット）を重ねることで遠くからでも一目で識別できるように改良
                if show_dotted:
                    for c_no in interest_cards:
                        if c_no in coords_dict:
                            ix, iy = coords_dict[c_no]['X'], coords_dict[c_no]['Y']
                            c_title = coords_dict[c_no]['見出し']
                            
                            # メインの太い点線
                            fig.add_trace(go.Scatter3d(
                                x=[cx, ix], y=[cy, iy], z=[z_offset, 0],
                                mode='lines',
                                line=dict(color=color, width=7.0, dash='dot'),
                                opacity=0.95,
                                showlegend=False,
                                hoverinfo='none'
                            ))
                            
                            # 視点が遠くても点線であることが一目でわかるよう、線上に等間隔のドットを配置
                            num_dots = 6
                            dot_xs = np.linspace(cx, ix, num_dots)
                            dot_ys = np.linspace(cy, iy, num_dots)
                            dot_zs = np.linspace(z_offset, 0, num_dots)
                            fig.add_trace(go.Scatter3d(
                                x=dot_xs[1:-1], y=dot_ys[1:-1], z=dot_zs[1:-1],
                                mode='markers',
                                marker=dict(size=4.5, color=color, symbol='circle'),
                                showlegend=False,
                                hoverinfo='none'
                            ))

            # ラベル表示
            if show_labels:
                lbl_x, lbl_y, lbl_z, lbl_text = [], [], [], []
                for c_no in related_card_nos:
                    if c_no in coords_dict:
                        c_info = coords_dict[c_no]
                        lbl_x.append(c_info['X'] + 0.03)
                        lbl_y.append(c_info['Y'] + 0.02)
                        lbl_z.append(0.005)
                        lbl_text.append(f"<b>{int(c_no)}. {c_info['見出し']}</b>")
                
                fig.add_trace(go.Scatter3d(
                    x=lbl_x, y=lbl_y, z=lbl_z,
                    mode='text',
                    text=lbl_text,
                    textfont=dict(size=10, color='#EFEFEF'),
                    showlegend=False,
                    hoverinfo='none'
                ))
            
            # ハート表示
            if show_hearts:
                for c_no, voters in interest_map.items():
                    if c_no in coords_dict:
                        c_info = coords_dict[c_no]
                        voters_str = "<br>".join(voters)
                        fig.add_trace(go.Scatter3d(
                            x=[c_info['X'] - 0.08], y=[c_info['Y'] + 0.06], z=[0.01],
                            mode='text',
                            text=[f"♥ {len(voters)}"],
                            textfont=dict(size=11, color='#FF69B4', family='Arial Black'),
                            hoverinfo='text',
                            hovertext=[f"<b>No.{c_no} {c_info['見出し']}</b><br>関心寄せた人:<br>{voters_str}"],
                            showlegend=False
                        ))

        # --- 3Dレイアウトの調整 ---
        fig.update_layout(
            title=dict(text=f'Interactive 3D Star Map: {selected_group}', font=dict(color='white', size=18)),
            paper_bgcolor='#0E1117',
            plot_bgcolor='#0E1117',
            scene=dict(
                xaxis=dict(showbackground=False, showgrid=False, zeroline=False, showticklabels=False, title=''),
                yaxis=dict(showbackground=False, showgrid=False, zeroline=False, showticklabels=False, title=''),
                zaxis=dict(showbackground=False, showgrid=False, zeroline=False, showticklabels=False, title='', range=[-0.05, 0.1]),
                bgcolor='#0E1117',
                camera=dict(
                    eye=dict(x=0, y=-0.1, z=2.2)
                )
            ),
            hovermode='closest',
            height=750,
            margin=dict(l=20, r=20, t=50, b=20),
            legend=dict(font=dict(color='white'))
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # 詳細データ表
        if show_hearts and selected_group != "（グループを選択しない：星図のみ）":
            st.markdown("### 💖 このグループの対話で関心を集めた星の詳細")
            interest_data = []
            for c_no in coords_dict:
                if c_no in interest_map:
                    c_info = coords_dict[c_no]
                    interest_data.append({
                        "No": int(c_no),
                        "星のタイトル": c_info['見出し'],
                        "関心の数 (♥)": len(interest_map[c_no]),
                        "関心を寄せた人": ", ".join(interest_map[c_no])
                    })
            if interest_data:
                st.dataframe(pd.DataFrame(interest_data), use_container_width=True)
            else:
                st.info("現在表示されている星には、まだ関心が寄せられていません。")
                
    except Exception as e:
        st.error(f"データの処理中にエラーが発生しました: {e}")
else:
    st.info("左側のサイドバーから「ナラティブ/座標データ」「イベント参加者データ」をアップロードしてください。")
