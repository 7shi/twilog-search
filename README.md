# Twilog ログ検索

Twilogのエクスポートデータからベクトル検索とタグ検索を可能にするデータ処理システム。

## データ概要

- **ソースデータ**: twilog.csv（227,011件のTwilogエクスポートデータ）
- **処理対象**: 投稿ID、URL、タイムスタンプ、コンテンツ、ログタイプ

## 実行手順

### 1. ベクトル化段階（必須）
```bash
uv run src/vectorize.py
```
- **入力**: twilog.csv（直接読み込み）
- **出力**: embeddings/ディレクトリ（226個の.safetensorsファイル）
- **処理内容**: Ruri3モデルによる1000件ずつの分割処理
- **処理時間**: 約1時間56分（GPU環境）
- **特徴**: 中断・再開機能対応、SQLiteデータベース不要

### 2. 検索サーバー起動段階
```bash
uv run src/twilog_server.py start
```
- **入力**: embeddings/ディレクトリ
- **機能**: WebSocketベースの検索サーバー（デーモン）
- **処理**: Ruri3モデル初期化 + 埋め込みデータ読み込み
- **起動時間**: 約85秒（初回のみ）
- **特徴**: バックグラウンド実行、複数クライアント対応

### 3. ベクトル検索段階
```bash
uv run src/search.py
```
- **入力**: twilog.csv + twilog_server.py（WebSocket通信）
- **機能**: 意味的検索による投稿発見（リモート検索）
- **表示**: ランク・類似度・ユーザー・日時・URL・内容
- **特徴**: 対話的検索インターフェース（フィルタリング機能は一時無効化）
- **コマンド**: `/help`でヘルプ（ユーザー・日付・表示件数設定は現在利用不可）
- **起動時間**: 数秒（軽量クライアント）
- **アーキテクチャ**: twilog_server.pyのsearch_similarメソッド使用

### 4. MCP統合段階（オプション）
```bash
# Node.js MCPサーバー起動と対話的クライアント
uv run src/mcp_wrap.py node -- /path/to/twilog-mcp-server/dist/index.js
```
- **Node.js MCPサーバー**: TypeScript実装のMCPラッパー（twilog-mcp-server）
- **MCPラッパー**: 対話的JSON-RPCクライアント（mcp_wrap.py）
- **機能**: ツール一覧表示、YAML出力、ヘルプ機能（`/help <tool_name>`）
- **対応ツール**: 類似検索、テキスト検索、統計情報取得、ベクトル化
- **アーキテクチャ**: twilog_server.pyへの単純ラッパー（SQLite不要）


## データフロー

```
twilog.csv (227,011件)
    ↓ vectorize.py (CSVから直接ベクトル化)
embeddings/ (226個の.safetensorsファイル + meta.json)
    ↓ twilog_server.py (WebSocketサーバー + SearchEngine統合 + MCP互換メソッド)
    ├─ search.py (軽量フロントエンド)
    └─ twilog-mcp-server (単純WebSocketラッパー) 
        └─ mcp_wrap.py (MCP対話的クライアント)
```

## 現在の状況

### 完了済み
- ベクトル化（vectorize.py）
- 検索サーバー（twilog_server.py）
- ベクトル検索（search.py）
- MCP統合（twilog-mcp-server + mcp_wrap.py）
- タグ付け（extract_tags.py）- CSVベース対応

## 出力ファイル

| ファイル | 件数 | 説明 |
|---------|------|------|
| embeddings/*.safetensors | 226ファイル | ベクトルデータ |
| tags/*.jsonl | 任意 | 自動生成タグ（オプション） |

## 技術仕様

- **データアクセス**: data_csv.py（CSV直接アクセス）
- **ベクトル化**: Ruri3モデル（日本語特化）
- **検索アーキテクチャ**: WebSocketベースのサーバー・クライアント分離
- **処理方式**: 分割処理による安全性確保
- **中断・再開**: vectorize.pyで対応
- **統合アーキテクチャ**: SearchEngine中心の一元化（MCP/CLI統一）

## 依存関係

主要なライブラリは`pyproject.toml`で管理。各スクリプトの詳細な実装理由は対応する`.md`ファイルを参照。

### 主要コンポーネント

- **search.py**: 軽量検索フロントエンド（表示のみ特化）
- **search_engine.py**: フィルタリング・重複除去の中核（twilog_server.pyで統合使用）
- **data_csv.py**: CSVベースデータアクセス層
- **twilog_client.py**: WebSocket通信クライアント
- **safe_input.py**: 安全な入力処理（日本語対応）
- **twilog_server.py**: 統合WebSocketサーバー（ベクトル検索 + SearchEngine + MCP互換メソッド）
- **mcp_wrap.py**: MCPプロトコル対話的クライアント
