# Twilog ログ検索

Twilogのエクスポートデータからベクトル検索とタグ検索を可能にするデータ処理システム。

## 概要

CSVデータをベクトル化し、意味的類似性に基づく検索を実現するシステムです。クライアント・サーバーアーキテクチャを採用しており、WebSocketベースの検索サーバーに対してCLIクライアントとMCPクライアントの両方からアクセス可能です。

- **データ処理**: CSVファイルをRuri v3モデルでベクトル化
- **検索方式**: 意味的類似性による高精度検索 + 複合検索（V|T構文）
- **アーキテクチャ**: WebSocketサーバー + 複数クライアント対応
- **クライアント**: CLI（search.py）とMCPサーバー（twilog-mcp-server）の2種類
- **実装言語**: サーバー・CLIクライアント（Python）、MCPサーバー（TypeScript）

## データ概要

- **ソースデータ**: twilog.csv（Twilogエクスポートデータ、UTF-8形式）
- **処理対象**: 投稿ID、URL、タイムスタンプ、コンテンツ、ログタイプ

## 実行手順

### 1. ベクトル化段階（必須）
```bash
uv run src/vectorize.py
```
- **入力**: twilog.csv（直接読み込み）
- **出力**: embeddings/ディレクトリ（.safetensorsファイル）
- **処理内容**: 1000件ずつの分割処理
- **処理時間**: 約1時間56分（GPU環境）
- **特徴**: 中断・再開機能対応、SQLiteデータベース不要

### 1-2. タグ付け段階（オプション）

#### リアルタイム処理
```bash
uv run src/add_tags.py twilog.csv
```
- **入力**: twilog.csv（直接読み込み）
- **出力**: tags/ディレクトリ（.jsonlファイル、1000件ずつ分割）
- **処理時間**: 約158時間（22万件、ローカルLLM）
- **特徴**: 1件ずつ処理・保存、中断・再開機能対応

#### バッチAPI処理（Gemini特化版）
```bash
# 1. バッチリクエスト生成
uv run src/generate_batch.py twilog.csv

# 2-3. バッチジョブ投入・ポーリング・結果取得
# 注意: submit_batch.pyとpoll_batch.pyは独立プロジェクトに移行しました
# 代替ツール: https://github.com/7shi/gemini-batch
```
- **generate_batch.py**: CSVからGeminiバッチAPI用JSONLリクエスト生成（1万件ずつ分割）
- **gemini-batch**: バッチジョブ管理用の独立ツール
  - 複数JSONLファイルの一括ジョブ投入・監視
  - TUIベースのリアルタイム進捗表示
  - 自動リソースクリーンアップ機能
  - インストール: `uv tool install https://github.com/7shi/gemini-batch.git`
- **処理時間**: リクエスト生成数分 + バッチ処理時間（大幅短縮期待）
- **特徴**: add_tags.pyのGemini特化版、コスト効率とスケーラビリティを重視

### 2. 検索サーバー起動段階
```bash
uv run src/twilog_server.py start
```
- **入力**: embeddings/ディレクトリ
- **機能**: WebSocketベースの検索サーバー（デーモン）
- **処理**: モデル初期化 + 埋め込みデータ読み込み
- **起動時間**: 約85秒（初回のみ）
- **特徴**: バックグラウンド実行、複数クライアント対応

### 3. ベクトル検索段階
```bash
uv run src/search.py
```
- **入力**: twilog.csv + twilog_server.py（WebSocket通信）
- **機能**: 意味的検索による投稿発見（リモート検索）
- **表示**: ランク・類似度・ユーザー・日時・URL・内容
- **特徴**: 対話的検索インターフェース（フィルタリング機能復活済み）
- **コマンド**: `/help`でヘルプ、`/user`でユーザーフィルタリング、`/date`で日付フィルタリング、`/top`で表示件数設定
- **検索構文**: 
  - `機械学習` - ベクトル検索のみ
  - `| "hello world" -spam` - テキスト検索のみ
  - `機械学習 | -spam` - ベクトル検索→テキスト絞り込み（複合検索）
- **起動時間**: 数秒（軽量クライアント）
- **アーキテクチャ**: twilog_server.pyのsearch_similarメソッド使用

### 4. MCP統合段階（オプション）
対話的クライアントからNode.js MCPサーバー起動
```bash
uv run src/mcp_wrap.py node -- /path/to/twilog-mcp-server/dist/index.js
```
- **Node.js MCPサーバー**: TypeScript実装のMCPラッパー（twilog-mcp-server）
- **MCPラッパー**: 対話的JSON-RPCクライアント（mcp_wrap.py）
- **機能**: ツール一覧表示、YAML出力、ヘルプ機能（`/help <tool_name>`）
- **対応ツール**: 類似検索、テキスト検索、統計情報取得、ベクトル化
- **フィルタリング**: SearchSettings対応（ユーザー・日付フィルタリング）
- **アーキテクチャ**: twilog_server.pyへの単純ラッパー（SQLite不要）
- **詳細**: [MCP サーバー詳細](mcp/README.md)


## データフロー

```
twilog.csv
    ├─ vectorize.py (CSVから直接ベクトル化)
    │   ↓
    │ embeddings/ (.safetensorsファイル + meta.json)
    │   ↓ twilog_server.py (WebSocketサーバー + SearchEngine統合 + MCP互換メソッド)
    │   ├─ search.py (軽量フロントエンド)
    │   └─ twilog-mcp-server (単純WebSocketラッパー) 
    │       └─ mcp_wrap.py (MCP対話的クライアント)
    └─ タグ付けパイプライン
        ├─ add_tags.py (リアルタイム処理) → tags/ (.jsonlファイル)
        └─ Gemini特化版
            ├─ generate_batch.py (バッチリクエスト生成) → batch/ (.jsonlファイル)
            └─ gemini-batch (独立ツール)
                ├─ gembatch submit (バッチジョブ投入) → Geminiバッチ処理
                └─ gembatch poll (ジョブポーリング・結果取得) → batch/results/ (.jsonlファイル)
```

## 現在の状況

### 完了済み
- ベクトル化（vectorize.py）
- 検索サーバー（twilog_server.py）
- ベクトル検索（search.py）
- V|T複合検索（パイプライン構文による統合）
- MCP統合（twilog-mcp-server + mcp_wrap.py）
- タグ付け（add_tags.py）- CSVベース、リアルタイム処理対応
- Gemini特化タグ付け（generate_batch.py + [gemini-batch](https://github.com/7shi/gemini-batch)）- バッチAPI処理対応

## 出力ファイル

| ファイル | 件数 | 説明 |
|---------|------|------|
| embeddings/*.safetensors | 複数ファイル | ベクトルデータ |
| tags/*.jsonl | 任意 | 自動生成タグ（リアルタイム処理） |
| batch/*.jsonl | 任意 | バッチAPIリクエスト（generate_batch.py生成） |
| batch/results/*.jsonl | 任意 | バッチ処理結果（gemini-batch取得） |

## 技術仕様

- **データアクセス**: data_csv.py（CSV直接アクセス）
- **ベクトル化**: Ruri v3モデル（日本語特化）
- **検索アーキテクチャ**: WebSocketベースのサーバー・クライアント分離
- **処理方式**: 分割処理による安全性確保
- **中断・再開**: vectorize.pyで対応
- **統合アーキテクチャ**: SearchEngine中心の一元化（MCP/CLI統一）
- **設定管理**: SearchSettings（ユーザー・日付フィルタリング、表示件数）、重複除去は常時有効
- **複合検索**: V|T構文（ベクトル|テキスト）による柔軟な検索組み合わせ

## 依存関係

主要なライブラリは`pyproject.toml`で管理。各スクリプトの詳細な実装理由は対応する`.md`ファイルを参照。

### 主要コンポーネント

- **search.py**: 軽量検索フロントエンド（設定管理＋表示特化）
- **search_engine.py**: フィルタリング・重複除去の中核（ステートレス設計、twilog_server.pyで統合使用）
- **settings.py**: 統合設定管理（SearchSettings、シリアライズ対応）
- **data_csv.py**: CSVベースデータアクセス層
- **twilog_client.py**: WebSocket通信クライアント（SearchSettings対応）
- **safe_input.py**: 安全な入力処理（日本語対応）
- **twilog_server.py**: 統合WebSocketサーバー（ベクトル検索 + SearchEngine + MCP互換メソッド + 設定デシリアライズ）
- **mcp_wrap.py**: MCPプロトコル対話的クライアント
