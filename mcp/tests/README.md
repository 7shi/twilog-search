# テストディレクトリ

Twilog MCP Serverのテストスイートです。Node.js標準のtest runnerを使用しています。

## 実行方法

### 基本的な実行（推奨）
```bash
# 全テスト実行（ユニット + 統合テスト）
npm test

# 監視モード（ファイル変更時に自動実行）
npm run test:watch

# ユニットテストのみ実行
npm run test:unit

# 統合テストのみ実行
npm run test:integration
```

### 個別ファイル実行（デバッグ用）
```bash
node --test tests/unit.test.js
node --test tests/basic.test.js
node --test tests/debug.test.js
node --test tests/date-filter.test.js
node --test tests/websocket-direct.test.js
```

### オプション付き実行
```bash
# データベースファイルを指定
npm test -- --db=/path/to/test.db

# WebSocketサーバーを指定
npm test -- --websocket=ws://localhost:9999

# 両方を指定
npm test -- --db=/path/to/test.db --websocket=ws://localhost:9999
```

## テストファイル構成

### メインテストファイル

#### `all.test.js` ⭐推奨
- **役割**: 全テストを統合した高速テストスイート
- **特徴**: 共有サーバー方式で1回の初期化のみ
- **実行時間**: 約19秒（従来の46%短縮）
- **テスト内容**: ユニットテスト + 統合テスト（基本機能、date_filter、デバッグ）

#### `unit.test.js`
- **役割**: ユニットテスト（個別モジュールのテスト）
- **特徴**: サーバー起動不要、高速実行
- **実行時間**: 約1秒未満
- **テスト内容**: TwilogFiltersクラスの日付フィルター機能

### サポートファイル

#### `base-client.js`
- **役割**: 共通テストヘルパー
- **機能**: 
  - `MCPTestClient`: MCP SDK使用のテストクライアント
  - `SharedMCPServer`: 共有サーバー管理クラス
  - `initializeSharedServer`/`cleanupSharedServer`: サーバーライフサイクル管理
  - `runMCPTest`: 個別サーバー起動版（後方互換性用）
  - `parseTestArgs`: コマンドライン引数解析

### 統合テストファイル（個別実行用）

#### `basic.test.js`
- **役割**: 基本機能の統合テスト
- **用途**: 基本機能のみを分離してテストしたい場合
- **テスト内容**:
  - サーバー状態確認（`get_status`）
  - データベース統計取得（`get_database_stats`）
  - ツール一覧取得（`tools/list`）

#### `debug.test.js`
- **役割**: デバッグ機能の統合テスト
- **用途**: デバッグ機能のみを分離してテストしたい場合
- **テスト内容**:
  - 短期間date_filterテスト（1週間範囲での検索）

#### `date-filter.test.js`
- **役割**: 日付フィルター機能の統合テスト
- **用途**: 日付フィルター機能のみを分離してテストしたい場合
- **テスト内容**:
  - 基本検索（フィルターなし）
  - 2022年以降のフィルター
  - 2023年以降のフィルター
  - 短期間フィルター（2024年7月）

#### `websocket-direct.test.js`
- **役割**: WebSocket直接通信のパフォーマンステスト
- **用途**: MCPを経由せずにTwilog Serverとの通信性能を測定
- **テスト内容**:
  - サーバー状態確認
  - 小規模検索（10件）
  - 中規模検索（100件）
  - 大規模検索（1000件）
  - 全件取得（分割送信プロトコル検証）

## テストの特徴

### パフォーマンス最適化

1. **共有サーバー方式**: テストスイート全体で1つのサーバーを共有
2. **高速初期化**: データベースキャッシュの初期化を1回のみ実行
3. **大幅な時間短縮**: 35.9秒 → 19.4秒（46%短縮）

### テスト分類

1. **ユニットテスト**: 個別モジュールの単体テスト（サーバー起動不要）
2. **統合テスト**: MCPサーバー全体のエンドツーエンドテスト
3. **共有サーバー方式**: 統合テスト全体で1つのサーバーを共有
4. **自動ビルド**: テスト実行前に自動的にTypeScriptをコンパイル

### アーキテクチャ

1. **MCP SDK使用**: 低レベルなJSON RPC通信を隠蔽
2. **Node.js標準test runner**: before/afterフックで適切なライフサイクル管理
3. **自動リソース管理**: クライアント接続の開始・終了を自動処理
4. **柔軟なオプション**: データベースパスとWebSocket URLを指定可能

## データベース設定

### デフォルトデータベース
- `--db`オプションを指定しない場合、プロジェクト親ディレクトリの`../twilog.db`が使用されます
- サーバー起動時に`--db`オプションでデータベースパスを指定可能

### ツール引数からdb_path削除
- ツール呼び出し時の`db_path`パラメータは削除されました
- データベース指定はサーバー起動時の`--db`オプションのみで行います

## 開発時の注意点

### 推奨実行方法
- **通常のテスト**: `npm test`（all.test.js）を使用
- **デバッグ時**: 個別ファイルを直接実行

### システム要件
- テスト実行時は自動的にMCPサーバーが起動されます
- 共有サーバー方式では1回の初期化で全テストを実行
- エラー時はリソースが適切にクリーンアップされます
- データベースの指定は重複していません（サーバー起動時のみ）

### パフォーマンス特性
- **初回実行**: データベースキャッシュの構築に約9秒
- **テスト実行**: キャッシュ済みデータで高速実行
- **メモリ使用量**: 226,866件の投稿データをメモリキャッシュ

## 新しいテストの追加指針

### 基本原則

1. **all.test.jsに追加することを優先** - パフォーマンスを保つため
2. **共有サーバーを活用** - 初期化コストを最小化
3. **適切なテストカテゴリに配置** - 既存のdescribeブロックを活用

### 追加手順

#### 1. all.test.jsに新しいテストを追加（推奨）

```javascript
describe('新機能テスト', () => {
  test('新機能のテスト', async () => {
    const client = getSharedClient();
    const result = await client.callTool('new_tool_name', args);
    assert.ok(result, 'テストが成功');
  });
});
```

#### 2. 新しい個別テストファイルを作成（特別な場合のみ）

新機能が以下の条件を満たす場合のみ個別ファイルを作成：
- **大量のテストケース**（10個以上）
- **特殊な設定が必要**（異なるDB、WebSocket設定等）
- **長時間実行**（他のテストに影響する場合）

##### ファイル作成時の注意点

```javascript
// 共有サーバー方式テンプレート
import { test, describe, before, after } from 'node:test';
import { initializeSharedServer, cleanupSharedServer, getSharedClient, parseTestArgs } from './base-client.js';

describe('新機能テスト', () => {
  before(async () => {
    await initializeSharedServer({ dbPath, websocketUrl });
  });

  after(async () => {
    await cleanupSharedServer();
  });

  // テストケース
});
```

##### 実行方法

新しいテストファイルの実行：

```bash
node --test tests/new-feature.test.js
```

### テスト作成のベストプラクティス

1. **明確なテスト名**: 何をテストしているかが分かる名前
2. **適切なアサーション**: 期待される結果を明確に検証
3. **エラーハンドリング**: 失敗時のメッセージを分かりやすく
4. **データの独立性**: テスト間でデータの依存関係を作らない

### パフォーマンス配慮

- **all.test.js優先**: 共有サーバーで高速実行
- **最小限のデータ**: テストに必要最小限のデータのみ使用
- **適切なtop_k**: 検索テストでは小さなtop_k値を使用
