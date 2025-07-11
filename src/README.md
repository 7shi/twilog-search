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
- **twilog_server.py**: embed_server.pyを継承した統合検索サーバー（SearchEngine統合、MCP互換メソッド提供）
- **twilog_client.py**: embed_client.pyを継承したTwilog検索クライアント（データソースに依存しない）

## 検索
- **search.py**: 軽量化された対話的検索フロントエンド（twilog_server.pyのsearch_similarメソッド使用、設定機能復活済み）
- **search_engine.py**: ベクトル検索結果の絞り込み・フィルタリング・重複除去を担当する検索エンジン（ステートレス設計、twilog_server.pyで統合使用）
- **text_proc.py**: 高度なテキスト検索のためのクエリパース機能（シェル風構文、クォート・エスケープ・除外条件サポート、V|T複合検索構文）
- **safe_input.py**: 安全なテキスト入力機能（readline履歴管理、検証機能）
- **settings.py**: 設定情報を格納するデータクラス（SearchSettings統合管理、シリアライズ対応）
- **settings_ui.py**: 設定UI機能を提供する純粋関数群（search.pyで復活使用）

## アーキテクチャ
このプロジェクトは責務分離を重視した統合設計を採用：

- **UI層**: search.py（軽量フロントエンド + 設定管理）、safe_input.py（入力処理）、settings_ui.py（設定UI）
- **統合サーバー層**: twilog_server.py（ベクトル検索 + SearchEngine統合 + MCP互換メソッド + 設定デシリアライズ + V|T複合検索）
- **ロジック層**: search_engine.py（ステートレス・フィルタリング処理中核）、settings.py（統合設定データ + シリアライズ）、text_proc.py（クエリパース）
- **データ層**: data_csv.py（CSVアクセス）
- **通信層**: twilog_client.py（WebSocket通信 + SearchSettings対応）、embed_server.py（サーバー基盤）

### 統合アーキテクチャの特徴
- **一元化**: SearchEngineをtwilog_server.pyで統合使用、重複実装を解消
- **統一API**: MCP/CLI両方で同じメソッド（search_similar、get_user_stats等）を使用
- **ステートレス**: SearchEngineから状態を削除、並行アクセス時の競合を解消
- **設定統合**: SearchSettingsによる3つの設定クラス統合管理、シリアライズ対応
- **軽量化**: search.pyは設定管理＋表示に特化、検索・フィルタリングはサーバー側で実行
- **ラッパー化**: MCPサーバーは単純なWebSocketラッパーとして簡素化
- **複合検索**: V|T構文による透過的なベクトル・テキスト複合検索（クライアント変更不要）

## データファイル
- **標準データファイル**: `twilog.csv`（デフォルト、引数省略可能）
- **データ形式**: CSVベース（SQLiteデータベース不要）

## MCP
- **mcp_wrap.py**: MCPサーバーとの対話的な通信ラッパー（データソースに依存しない）
