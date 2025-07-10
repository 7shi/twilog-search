# MCPサーバー手動テスト方法

## 方法1: 自動テストクライアント

```bash
# デフォルトデータベース (twilog.db) でテスト
node test-client.js

# カスタムデータベースでテスト
node test-client.js --db /path/to/custom.db

# WebSocketサーバーも指定
node test-client.js --db custom.db --websocket ws://localhost:9999

# ヘルプ表示
node test-client.js --help
```

このクライアントは：
- MCPサーバーを自動起動
- 初期化メッセージを送信
- ツール一覧を取得
- 基本的なツールを実行
- レスポンスを表示

## 方法2: 手動stdin/stdout通信

### ステップ1: サーバー起動
```bash
# デフォルトデータベース (twilog.db)
npm start

# カスタムデータベース指定
npm start -- --db /path/to/custom.db
node dist/index.js --database mydata.db

# WebSocketサーバーも指定
node dist/index.js --db custom.db --websocket ws://localhost:9999
```

### ステップ2: 別ターミナルで通信テスト

```bash
# 初期化メッセージ
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"clientInfo":{"name":"test","version":"1.0.0"}}}' | npm start

# ツール一覧取得
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | npm start

# サーバー状態確認
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_status","arguments":{}}}' | npm start
```

## 方法3: Node.js REPLで対話テスト

```bash
node -e "
const { spawn } = require('child_process');
const server = spawn('npm', ['start'], { stdio: ['pipe', 'pipe', 'inherit'] });

server.stdout.on('data', (data) => {
  console.log('レスポンス:', data.toString());
});

// 初期化
server.stdin.write(JSON.stringify({
  jsonrpc: '2.0',
  id: 1,
  method: 'initialize',
  params: {
    protocolVersion: '2024-11-05',
    capabilities: { tools: {} },
    clientInfo: { name: 'test', version: '1.0.0' }
  }
}) + '\\n');

setTimeout(() => {
  // ツール一覧
  server.stdin.write(JSON.stringify({
    jsonrpc: '2.0',
    id: 2,
    method: 'tools/list'
  }) + '\\n');
}, 1000);

setTimeout(() => process.exit(0), 5000);
"
```

## 方法4: Claude Desktop連携テスト

### claude_desktop_config.json に追加:

**デフォルトデータベース (twilog.db):**
```json
{
  "mcpServers": {
    "twilog": {
      "command": "node",
      "args": ["/path/to/twilog-mcp-server/dist/index.js"]
    }
  }
}
```

**カスタムデータベース指定:**
```json
{
  "mcpServers": {
    "twilog": {
      "command": "node",
      "args": [
        "/path/to/twilog-mcp-server/dist/index.js",
        "--db",
        "/path/to/custom.db"
      ]
    }
  }
}
```

**開発モード (npm使用):**
```json
{
  "mcpServers": {
    "twilog-dev": {
      "command": "npm",
      "args": ["start", "--", "--db", "/path/to/custom.db"],
      "cwd": "/path/to/twilog-mcp-server"
    }
  }
}
```

**WebSocketサーバーも指定:**
```json
{
  "mcpServers": {
    "twilog": {
      "command": "node",
      "args": [
        "/path/to/twilog-mcp-server/dist/index.js",
        "--db", "/path/to/custom.db",
        "--websocket", "ws://localhost:9999"
      ]
    }
  }
}
```

## テスト用JSONメッセージ例

### 初期化
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {}
    },
    "clientInfo": {
      "name": "test-client",
      "version": "1.0.0"
    }
  }
}
```

### ツール一覧取得
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list"
}
```

### 検索実行
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "search_similar",
    "arguments": {
      "query": "プログラミング",
      "top_k": 5
    }
  }
}
```

**カスタムDB指定時:**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "search_similar",
    "arguments": {
      "query": "プログラミング",
      "top_k": 5,
      "db_path": "/path/to/custom.db"
    }
  }
}
```

### ユーザー統計取得
```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "get_user_stats",
    "arguments": {
      "limit": 10
    }
  }
}
```

## 期待されるレスポンス例

成功時のツール一覧レスポンス:
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "search_similar",
        "description": "Twilogデータベースに対してベクトル検索を実行します"
      },
      {
        "name": "get_status", 
        "description": "Twilog Serverの稼働状況を確認します"
      }
    ]
  }
}
```

## トラブルシューティング

### よくあるエラー

1. **Twilog Server未起動**
   ```
   エラー: Twilog Serverに接続できません
   ```
   → `uv run get_server.py start` でTwilog Serverを起動

2. **データベースファイル未存在**
   ```
   エラー: データベース接続エラー
   ```
   → データベースファイルの存在確認
   → `--db`オプションでパス指定
   
   ```bash
   # 正しいパスを指定
   node dist/index.js --db /correct/path/to/twilog.db
   ```

3. **WebSocket接続失敗**
   ```
   エラー: WebSocket接続エラー
   ```
   → localhost:8765 でTwilog Serverが稼働しているか確認