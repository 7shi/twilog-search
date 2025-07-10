# Twilog MCP Server

Twilog検索システム用のMCP（Model Context Protocol）サーバーです。Twilog ServerへのWebSocket接続とSQLiteデータベース操作を統合したツールセットを提供します。

## 機能

### 主要ツール

1. **search_similar** - ベクトル検索
   - Twilog Serverを通じた意味的検索
   - ユーザーフィルタリング（includes/excludes/threshold）
   - 日付フィルタリング（from/to）
   - 重複除去機能

2. **get_status** - サーバー状態確認
   - Twilog Serverの稼働状況確認
   - 初期化完了状態の確認

3. **get_user_stats** - ユーザー統計
   - ユーザー別投稿数ランキング

4. **get_database_stats** - データベース統計
   - 総投稿数、ユーザー数、データ期間

5. **search_posts_by_text** - テキスト検索
   - LIKE検索による文字列マッチング

## セットアップ

### 前提条件

1. **Twilog Server** が稼働中であること
   ```bash
   uv run get_server.py start
   ```

2. **データベースファイル** が存在すること
   - デフォルト: `twilog.db`
   - カスタムパスも指定可能（`--db`オプション使用）

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

# カスタムデータベースファイルを指定
npm start -- --db /path/to/custom.db

# WebSocket URLも指定
npm start -- --db mydata.db --websocket ws://localhost:9999
```

### コマンドライン引数

```bash
node dist/index.js [オプション]

オプション:
  --db, --database PATH       デフォルトのデータベースファイルパス (デフォルト: twilog.db)
  --websocket, --ws URL       WebSocket URL (デフォルト: ws://localhost:8765)
  --help, -h                  ヘルプを表示

例:
  node dist/index.js --db /path/to/custom.db
  node dist/index.js --db=mydata.db --websocket=ws://localhost:8765
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

### フィルタリング付き検索

```typescript
{
  "name": "search_similar",
  "arguments": {
    "query": "プログラミング",
    "top_k": 20,
    "user_filter": {
      "threshold_min": 10
    },
    "date_filter": {
      "from": "2023-01-01 00:00:00",
      "to": "2023-12-31 23:59:59"
    }
  }
}
```

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
│   ├── index.ts      # メインサーバー
│   ├── database.ts   # データベース操作
│   └── filters.ts    # フィルタリング機能
├── package.json
├── tsconfig.json
└── README.md
```

### データフロー

1. MCP クライアント → MCP Server
2. MCP Server → Twilog Server (WebSocket)
3. MCP Server → SQLite データベース
4. フィルタリング処理
5. 結果の統合・整形
6. MCP クライアントへ返却

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

カスタムデータベースやWebSocketサーバーを使用する場合：

```json
{
  "mcpServers": {
    "twilog": {
      "command": "node",
      "args": ["dist/index.js", "--db", "/path/to/custom.db", "--websocket", "ws://localhost:9999"],
      "cwd": "/path/to/twilog-mcp-server",
      "env": {}
    }
  }
}
```

### Gemini CLI での設定例

`.gemini/settings.json` に以下の設定を追加：

```json
{
  "mcpServers": {
    "twilog": {
      "type": "stdio",
      "command": "node",
      "args": [
        "/path/to/twilog-mcp-server/dist/index.js",
        "--db",
        "/path/to/twilog.db"
      ],
      "env": {}
    }
  }
}
```

### WebSocket URL

デフォルト: `ws://localhost:8765`

各ツールで `websocket_url` パラメータによる上書きが可能です。

### データベースパス

**サーバー起動時にデフォルト指定:**
```bash
# デフォルト (twilog.db)
npm start

# カスタムデータベース
npm start -- --db /path/to/mydata.db
node dist/index.js --database custom.db
```

**注意:** ツール実行時の`db_path`パラメータは削除されました。データベース指定はサーバー起動時のみ可能です。

## フィルタリング機能

### ユーザーフィルタリング

- **includes**: 指定ユーザーのみを対象（排他的）
- **excludes**: 指定ユーザーを除外（排他的）
- **threshold_min**: 投稿数下限（組み合わせ可能）
- **threshold_max**: 投稿数上限（組み合わせ可能）

### 日付フィルタリング

- **from**: 開始日時（YYYY-MM-DD HH:MM:SS形式）
- **to**: 終了日時（YYYY-MM-DD HH:MM:SS形式）

### 重複除去

同一ユーザーの同一内容投稿について、より古い投稿を優先して表示します。

## エラーハンドリング

- WebSocket接続エラー
- データベース接続エラー
- 不正なクエリパラメータ
- サーバー応答エラー

すべてのエラーは適切なエラーメッセージと共にMCPクライアントに返却されます。

## テスト

### テスト実行

```bash
# 全テスト実行（ユニット + 統合テスト）
npm test

# ユニットテストのみ（高速、サーバー起動不要）
npm run test:unit

# 統合テストのみ（MCPサーバー経由）
npm run test:integration

# 監視モード（ファイル変更時に自動実行）
npm run test:watch
```

### テスト構成

- **ユニットテスト**: 個別モジュールの単体テスト（TwilogFiltersなど）
- **統合テスト**: MCPサーバー全体のエンドツーエンドテスト
- **共有サーバー方式**: 統合テスト全体で1つのサーバーを共有（46%高速化）

### テストオプション

```bash
# カスタムデータベースでテスト
npm test -- --db=/path/to/test.db

# WebSocketサーバーを指定してテスト
npm test -- --websocket=ws://localhost:9999
```

詳細な情報は [tests/README.md](tests/README.md) を参照してください。

## 開発

### 開発モード実行

```bash
npm run dev
```

### ウォッチモード

```bash
npm run watch
```

## ライセンス

MIT
