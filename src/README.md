# Pythonファイル分類

プロジェクト内のPythonファイルをデータアクセス方法によって分類。

1. **vectorize.py** - CSVから直接ベクトル化
2. **twilog_server.py** - 検索サーバー起動
3. **search.py** - 対話的検索インターフェース
4. **extract_tags.py** - タグ付け（オプション）

## ユーティリティ
- **read_csv.py**: 単純なCSVファイル読み込み（データ確認用、特定のデータソースに依存しない）

## データアクセス層
- **data_csv.py**: CSVファイルから直接データを読み込む専用のデータアクセス層

## 前処理
- **vectorize.py**: data_csv.pyをインポートして使用し、CSVファイルから直接データを読み込んでベクトル化を行う
- **extract_tags.py**: data_csv.pyを使用してCSVファイルから直接データを読み込み、strip_content関数で前処理を適用してタグ付けを行う

## サーバー・クライアント基盤
- **embed_server.py**: ベクトル化サーバーの基盤実装（データソースに依存しない）
- **embed_client.py**: ベクトル化サーバーへのクライアント実装（データソースに依存しない）
- **twilog_server.py**: embed_server.pyを継承したTwilog検索サーバー（データソースに依存しない）
- **twilog_client.py**: embed_client.pyを継承したTwilog検索クライアント（データソースに依存しない）

## 検索
- **search.py**: 対話的検索インターフェースとコマンド処理を担当するメインクライアント
- **search_engine.py**: ベクトル検索結果の絞り込み・フィルタリング・重複除去を担当する検索エンジン
- **safe_input.py**: 安全なテキスト入力機能（readline履歴管理、検証機能）
- **settings.py**: 設定情報を格納するデータクラス（ユーザー・日付フィルタリング、表示件数設定）
- **settings_ui.py**: 設定UI機能を提供する純粋関数群

## アーキテクチャ
このプロジェクトは責務分離を重視した設計を採用：

- **UI層**: search.py（対話的インターフェース）、settings_ui.py（設定UI）、safe_input.py（入力処理）
- **ロジック層**: search_engine.py（検索処理）、settings.py（設定データ）
- **データ層**: data_csv.py（CSVアクセス）
- **通信層**: twilog_client.py（WebSocket通信）、twilog_server.py（検索サーバー）

## データファイル
- **標準データファイル**: `twilog.csv`（デフォルト、引数省略可能）
- **データ形式**: CSVベース（SQLiteデータベース不要）

## MCP
- **mcp_wrap.py**: MCPサーバーとの対話的な通信ラッパー（データソースに依存しない）
