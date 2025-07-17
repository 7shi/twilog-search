# Pythonファイル分類

プロジェクト内のPythonファイルを機能別・接頭辞別に分類。

## ツール群別の詳細

### 主要処理フロー
- **vectorize.py** - CSVから直接ベクトル化、中断・再開機能対応
- **twilog_server.py** - embed_server.pyを継承した統合検索サーバー、SearchEngine統合、MCP互換メソッド提供、meta.jsonからCSVパス自動取得
- **search.py** - 軽量化された対話的検索フロントエンド、twilog_server.pyのsearch_similarメソッド使用
- **add_tags.py** - data_csv.pyを使用、CSVファイルから直接データ読み込み、strip_content関数で前処理適用、タグ付け（オプション）

### バッチ処理パイプライン（batch_*）
使用順序に従った5段階のバッチ処理パイプライン：
- **batch_generate.py**: data_csv.pyを使用してCSVファイルから直接データを読み込み、GeminiバッチAPI用のJSONLリクエストファイルを生成する（1万件ずつ分割）
- **batch_usage.py**: バッチ処理結果の使用統計とコスト計算、candidates構造の検証、データ品質確認
- **batch_merge.py**: 複数バッチ結果ファイルの統合マージ、重複除去、データ整合性チェック
- **batch_vectorize.py**: vectorize.pyの汎用化された関数を再利用し、JSONLファイルのreasoningとsummaryフィールドを個別にベクトル化

### ベクトル化基盤（embed_*）
- **embed_server.py**: ベクトル化サーバーの基盤実装、デーモン管理、WebSocket通信、エラーハンドリング
- **embed_client.py**: ベクトル化サーバーへのクライアント基盤実装、WebSocket通信抽象化
- **twilog_client.py**: embed_client.pyを継承したTwilog検索クライアント、SearchSettings対応

### 検索関連（search_*）
- **search_engine.py**: ベクトル検索結果の絞り込み・フィルタリング・重複除去、ステートレス設計
- **vector_store.py**: ベクトルストア管理機能

### 設定管理（settings_*）
- **settings.py**: SearchSettings統合管理、シリアライズ対応、ユーザー・日付フィルタリング設定
- **settings_ui.py**: 設定UI機能の純粋関数群、search.pyで使用
- **user_info.py**: ユーザー情報管理クラス、Tab補完機能（キャッシュ機能付き）、レーベンシュタイン距離による類似ユーザー提案

### データアクセス（data_*）
- **data_csv.py**: CSVファイルから直接データを読み込む専用のデータアクセス層
- **read_csv.py**: 単純なCSVファイル読み込み、データ確認用

### 単独機能ツール
- **text_proc.py**: クエリパース機能、シェル風構文、クォート・エスケープ・除外条件サポート、V|T複合検索構文
- **safe_input.py**: 安全なテキスト入力機能、readline履歴管理、検証機能
- **command.py**: コマンドシステム基盤、@commandデコレーター、Tab補完機能
- **mcp_wrap.py**: MCPサーバーとの対話的通信ラッパー、JSON-RPCクライアント
- **batch_reader.py**: バッチ処理結果読み込み専用モジュール、遅延初期化対応

## アーキテクチャ
このプロジェクトは責務分離を重視した統合設計を採用：

- **UI層**: search.py（軽量フロントエンド + 設定管理）、safe_input.py（入力処理）、settings_ui.py（設定UI）、command.py（コマンド処理基盤）
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
