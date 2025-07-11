# Twilog MCP Server

Twilog検索システム用のMCP（Model Context Protocol）サーバーです。twilog_server.pyへの軽量WebSocketラッパーとして動作し、統一されたAPIを提供します。

## 機能

### 主要ツール

1. **search_similar** - ベクトル検索
   - twilog_server.pyを通じた意味的検索
   - SearchEngineによるフィルタリング（サーバー側処理）
   - 重複除去機能
   - SearchSettings対応（ユーザー・日付フィルタリング、表示件数制御）

2. **get_status** - サーバー状態確認
   - twilog_server.pyの稼働状況確認
   - SearchEngine初期化完了状態の確認

3. **get_user_stats** - ユーザー統計
   - ユーザー別投稿数ランキング

4. **get_database_stats** - データベース統計
   - 総投稿数、ユーザー数、データ期間

5. **search_posts_by_text** - テキスト検索
   - LIKE検索による文字列マッチング

6. **embed_text** - ベクトル化
   - テキストのベクトル化（デバッグ用）

## セットアップ

### 前提条件

1. **twilog_server.py** が稼働中であること
   ```bash
   uv run src/twilog_server.py start
   ```

2. **CSVファイルとembeddingsディレクトリ** が存在すること
   - twilog.csv（元データ）
   - embeddings/ ディレクトリ（ベクトルデータ + meta.json）
   - CSVパスはmeta.jsonから自動取得

### インストール

```bash
cd twilog-mcp-server
npm install
```

### ビルド

```bash
npm run build
```

### 実行

```bash
# 開発モード
npm run dev

# 本番実行
npm start

# WebSocket URLを指定
npm start -- --websocket ws://localhost:8765
```

### コマンドライン引数

```bash
node dist/index.js [オプション]

オプション:
  --websocket, --ws URL       WebSocket URL (デフォルト: ws://localhost:8765)
  --help, -h                  ヘルプを表示

例:
  node dist/index.js --websocket=ws://localhost:8765
```

## 使用例

### 基本的なベクトル検索

```typescript
// MCP クライアントから呼び出し
{
  "name": "search_similar",
  "arguments": {
    "query": "機械学習"
  }
}
```

### 件数制限付き検索

```typescript
{
  "name": "search_similar",
  "arguments": {
    "query": "プログラミング",
    "top_k": 20
  }
}
```

### 詳細なフィルタリング設定付き検索

```typescript
{
  "name": "search_similar",
  "arguments": {
    "query": "機械学習",
    "top_k": 20,
    "user_filter": {
      "includes": ["user1", "user2"],
    },
    "date_filter": {
      "from": "2023-01-01 00:00:00",
      "to": "2023-12-31 23:59:59"
    },
    "remove_duplicates": true
  }
}
```

**個別パラメータ対応**: `user_filter`、`date_filter`、`top_k`、`remove_duplicates`を個別に指定可能。MCPサーバー内部でSearchSettings形式に変換してサーバーに送信。

### ユーザー統計取得

```typescript
{
  "name": "get_user_stats",
  "arguments": {
    "limit": 100
  }
}
```

## アーキテクチャ

### ディレクトリ構造

```
twilog-mcp-server/
├── src/
│   ├── index.ts      # メインサーバー（WebSocketラッパー）
│   └── index.md      # 実装ドキュメント
├── package.json
├── tsconfig.json
└── README.md
```

**削除されたファイル**:
- `database.ts` - SQLiteアクセス層（不要）
- `filters.ts` - 独自フィルタリング（SearchEngineに統合）

### データフロー

1. MCP クライアント → MCP Server
2. MCP Server → twilog_server.py (WebSocket/JSON-RPC 2.0)
3. twilog_server.py → SearchEngine → CSV データ
4. フィルタリング・検索処理（サーバー側）
5. 結果の整形・返却
6. MCP クライアントへ表示

## 設定

### Claude Code での設定例

`.mcp.json` に以下の設定を追加：

```json
{
  "mcpServers": {
    "twilog": {
      "command": "node",
      "args": ["dist/index.js"],
      "cwd": "/path/to/twilog-mcp-server",
      "env": {}
    }
  }
}
```

カスタムWebSocketサーバーを使用する場合：

```json
{
  "mcpServers": {
    "twilog": {
      "command": "node",
      "args": ["dist/index.js", "--websocket", "ws://localhost:9999"],
      "cwd": "/path/to/twilog-mcp-server",
      "env": {}
    }
  }
}
```

### Gemini CLI での設定例

`.gemini/settings.json` に `.mcp.json` と同様の内容を記述。

### WebSocket URL

デフォルト: `ws://localhost:8765`

各ツールで `websocket_url` パラメータによる上書きが可能です。

### データ設定

**CSVファイルとembeddingsディレクトリ:**
- CSVパスは`embeddings/meta.json`から自動取得
- twilog_server.py起動時に設定が確定
- MCPサーバーでは設定変更不可（ラッパーのため）

**WebSocket URL:**
```bash
# デフォルト (ws://localhost:8765)
npm start

# カスタムURL
npm start -- --websocket ws://localhost:9999
```

## 処理の統合

### SearchEngine統合

全ての検索・フィルタリング処理はtwilog_server.py側のSearchEngineで実行されます：

- **ユーザーフィルタリング**: includes/excludes、投稿数閾値によるフィルタリング
- **日付フィルタリング**: from/to による期間指定フィルタリング
- **重複除去**: 同一ユーザー・同一内容の投稿で古い投稿を優先
- **ランキング**: 類似度順でのソート
- **SearchSettings**: CLIクライアントと完全に同一の設定形式をサポート

### ラッパーとしての役割

MCPサーバーは以下の処理のみを担当：
- JSON-RPC 2.0リクエストの転送
- twilog_server.pyからの結果受信
- MCP形式での結果フォーマット

## エラーハンドリング

- WebSocket接続エラー（ECONNREFUSED、ETIMEDOUT）
- JSON-RPC 2.0プロトコルエラー
- twilog_server.py応答エラー
- 不正なクエリパラメータ

すべてのエラーは適切な日本語エラーメッセージと共にMCPクライアントに返却されます。

## テスト

### 前提条件

twilog_server.pyが稼働していることを確認してください：

```bash
uv run src/twilog_server.py start
```

### テスト実行

```bash
# 基本テスト（WebSocket通信確認）
npm test

# カスタムWebSocketサーバーでテスト
npm test -- --websocket=ws://localhost:9999
```

### テスト内容

- WebSocket接続テスト
- JSON-RPC 2.0通信テスト  
- 各ツール（search_similar、get_status等）の動作確認
- エラーハンドリング確認

## 開発

### 開発モード実行

```bash
npm run dev
```

### アーキテクチャ

本MCPサーバーは **twilog_server.pyへの軽量ラッパー** として設計されています：

- **責務**: JSON-RPC 2.0通信とMCP形式への変換のみ
- **処理**: 検索・フィルタリングは全てtwilog_server.py側で実行
- **利点**: 機能追加時はtwilog_server.pyのみ修正すればCLI・MCP両方に反映
