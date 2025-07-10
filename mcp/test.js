#!/usr/bin/env node

import { spawn } from 'child_process';

// コマンドライン引数の解析
function parseTestArgs() {
  const args = process.argv.slice(2);
  const result = {};

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    
    if (arg === '--help' || arg === '-h') {
      result.help = true;
    } else if (arg === '--db' || arg === '--database') {
      result.dbPath = args[++i];
    } else if (arg === '--websocket' || arg === '--ws') {
      result.websocketUrl = args[++i];
    } else if (arg === '--mode' || arg === '-m') {
      result.testMode = args[++i];
    } else if (arg.startsWith('--db=')) {
      result.dbPath = arg.split('=')[1];
    } else if (arg.startsWith('--websocket=')) {
      result.websocketUrl = arg.split('=')[1];
    } else if (arg.startsWith('--mode=')) {
      result.testMode = arg.split('=')[1];
    }
  }

  return result;
}

function showTestHelp() {
  console.log(`Twilog MCP Server 統合テストクライアント

使用方法:
  node test.js [オプション]

オプション:
  --db, --database PATH       テスト用データベースファイルパス
  --websocket, --ws URL       WebSocket URL
  --mode, -m MODE             テストモード: all, basic, debug, date_filter
  --help, -h                  このヘルプを表示

テストモード:
  all         全種類のテスト（デフォルト）
  basic       基本的な機能テスト
  debug       デバッグモード（短期間のdate_filterテスト）
  date_filter 日付フィルターテスト（複数の期間でテスト）

例:
  node test.js
  node test.js --mode=debug
  node test.js --mode=date_filter --db /path/to/test.db
  node test.js --db=custom.db --websocket=ws://localhost:9999
`);
}

// 統合テストクライアント
class TwilogTestClient {
  constructor(dbPath, websocketUrl) {
    this.serverProcess = null;
    this.messageId = 1;
    this.dbPath = dbPath;
    this.websocketUrl = websocketUrl;
    this.testMode = 'all'; // 'all', 'basic', 'debug', 'date_filter'
    this.pendingRequests = new Map(); // messageId -> Promise resolver
  }

  async start() {
    console.log('MCPサーバーを起動中...');
    if (this.dbPath) {
      console.log(`データベース: ${this.dbPath}`);
    }
    if (this.websocketUrl) {
      console.log(`WebSocket URL: ${this.websocketUrl}`);
    }
    
    // MCPサーバープロセスを直接起動（npmを経由しない）
    const args = [];
    if (this.dbPath) {
      args.push('--db', this.dbPath);
    }
    if (this.websocketUrl) {
      args.push('--websocket', this.websocketUrl);
    }
    
    this.serverProcess = spawn('node', ['dist/index.js', ...args], {
      stdio: ['pipe', 'pipe', 'inherit'],
      cwd: process.cwd()
    });

    // デバッグモードでのレスポンス監視
    if (this.testMode === 'debug') {
      this.receivedResponses = 0;
      this.expectedResponses = 2; // initialize + search
    }

    this.serverProcess.stdout.on('data', (data) => {
      const response = data.toString().trim();
      if (response) {
        console.log('サーバーレスポンス:', response);
        try {
          const parsed = JSON.parse(response);
          console.log('パース済み:', JSON.stringify(parsed, null, 2));
          
          // レスポンスIDに対応するPromiseを解決
          if (parsed.id && this.pendingRequests.has(parsed.id)) {
            const resolver = this.pendingRequests.get(parsed.id);
            this.pendingRequests.delete(parsed.id);
            resolver(parsed);
          }
          
          // デバッグモードでのレスポンスカウント
          if (this.testMode === 'debug' && parsed.id) {
            this.receivedResponses++;
            console.log(`[${this.receivedResponses}/${this.expectedResponses}] レスポンス受信`);
            
            if (this.receivedResponses >= this.expectedResponses) {
              setTimeout(() => {
                console.log('\n=== テスト完了 - 正常終了 ===');
                this.stop();
                process.exit(0);
              }, 1000);
            }
          }
        } catch (e) {
          console.log('JSON以外のレスポンス:', response);
        }
      }
    });

    this.serverProcess.on('error', (error) => {
      console.error('サーバーエラー:', error);
    });

    // サーバー初期化待機（データキャッシュ初期化を待つ）
    setTimeout(() => {
      this.runTests();
    }, 10000);
  }

  sendMessage(message) {
    console.log('送信:', JSON.stringify(message));
    this.serverProcess.stdin.write(JSON.stringify(message) + '\n');
  }

  async sendMessageAndWait(message) {
    // messageIdとjsonrpcを自動で振る
    const messageId = this.messageId++;
    const messageWithDefaults = {
      jsonrpc: '2.0',
      id: messageId,
      ...message
    };
    
    return new Promise((resolve, reject) => {
      this.pendingRequests.set(messageId, resolve);
      this.sendMessage(messageWithDefaults);
      
      // タイムアウト設定（10秒）
      setTimeout(() => {
        if (this.pendingRequests.has(messageId)) {
          this.pendingRequests.delete(messageId);
          reject(new Error(`タイムアウト: メッセージID ${messageId} のレスポンス待機`));
        }
      }, 10000);
    });
  }

  async runTests() {
    switch (this.testMode) {
      case 'all':
        await this.runAllTests();
        break;
      case 'debug':
        await this.runDebugTests();
        break;
      case 'date_filter':
        await this.runDateFilterTests();
        break;
      case 'basic':
        await this.runBasicTests();
        break;
      default:
        await this.runAllTests();
    }
  }

  async runAllTests() {
    console.log('\n=== 全種類テスト開始 ===\n');

    // 1. 基本機能テスト
    console.log('\n--- 基本機能テスト ---');
    await this.runBasicTestsCore();

    console.log('\n--- 区切り線 ---');
    await this.sleep(2000);

    // 2. デバッグテスト（短期間検索）
    console.log('\n--- デバッグテスト ---');
    await this.runDebugTestsCore();

    console.log('\n--- 区切り線 ---');
    await this.sleep(2000);

    // 3. 日付フィルターテスト
    console.log('\n--- 日付フィルターテスト ---');
    await this.runDateFilterTestsCore();

    console.log('\n=== 全種類テスト完了 ===');
    console.log('サーバーを停止しています...');
    
    this.stop();
    setTimeout(() => {
      process.exit(0);
    }, 2000);
  }

  async runBasicTests() {
    await this.runBasicTestsCore();
    
    console.log('\n=== 基本テスト完了 ===');
    console.log('サーバーを停止しています...');
    
    this.stop();
    setTimeout(() => {
      process.exit(0);
    }, 2000);
  }

  async runBasicTestsCore() {
    console.log('\n=== 基本テスト開始 ===\n');

    // 1. 初期化
    await this.sendMessageAndWait({
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: {
          tools: {}
        },
        clientInfo: {
          name: 'twilog-test-client',
          version: '1.0.0'
        }
      }
    });

    // 2. ツール一覧取得
    await this.sendMessageAndWait({
      method: 'tools/list'
    });

    // 3. サーバー状態確認テスト
    await this.sendMessageAndWait({
      method: 'tools/call',
      params: {
        name: 'get_status',
        arguments: {}
      }
    });

    // 4. データベース統計テスト
    const dbStatsArgs = {};
    if (this.dbPath) {
      dbStatsArgs.db_path = this.dbPath;
    }
    
    await this.sendMessageAndWait({
      method: 'tools/call',
      params: {
        name: 'get_database_stats',
        arguments: dbStatsArgs
      }
    });

    // 5. embed_textテスト（新機能）
    console.log('\n--- embed_textテスト ---');
    await this.sendMessageAndWait({
      method: 'tools/call',
      params: {
        name: 'embed_text',
        arguments: {
          text: 'テスト用のテキストをベクトル化'
        }
      }
    });

  }

  async runDebugTests() {
    await this.runDebugTestsCore();
    
    console.log('\n=== テスト完了 - 正常終了 ===');
    this.stop();
    setTimeout(() => {
      process.exit(0);
    }, 2000);
  }

  async runDebugTestsCore() {
    console.log('\n=== デバッグテスト開始 ===\n');

    // 1. 初期化
    await this.sendMessageAndWait({
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: { tools: {} },
        clientInfo: { name: 'debug-test', version: '1.0.0' }
      }
    });

    // 2. 短期間のdate_filterテスト
    console.log('\n--- 短期間date_filterテスト ---');
    await this.sendMessageAndWait({
      method: 'tools/call',
      params: {
        name: 'search_similar',
        arguments: {
          query: 'テスト',
          top_k: 3,
          date_filter: {
            from: '2024-07-01 00:00:00',
            to: '2024-07-07 23:59:59'  // 1週間に短縮
          }
        }
      }
    });

    // 3. embed_textテスト（デバッグ用）
    console.log('\n--- embed_textテスト（デバッグ用） ---');
    await this.sendMessageAndWait({
      method: 'tools/call',
      params: {
        name: 'embed_text',
        arguments: {
          text: 'デバッグ用のサンプルテキスト'
        }
      }
    });

  }

  async runDateFilterTests() {
    await this.runDateFilterTestsCore();
    
    console.log('\n=== テスト完了 ===');
    console.log('サーバーを停止しています...');
    
    this.stop();
    setTimeout(() => {
      process.exit(0);
    }, 2000);
  }

  async runDateFilterTestsCore() {
    console.log('\n=== date_filter テスト開始 ===\n');

    // 1. 初期化
    await this.sendMessageAndWait({
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: {
          tools: {}
        },
        clientInfo: {
          name: 'date-filter-test-client',
          version: '1.0.0'
        }
      }
    });

    // 2. ツール一覧取得
    await this.sendMessageAndWait({
      method: 'tools/list'
    });

    // 3. 基本的な検索テスト（フィルターなし）
    console.log('\n--- 基本検索テスト ---');
    const baseArgs = {
      query: 'テスト',
      top_k: 5
    };
    if (this.dbPath) {
      baseArgs.db_path = this.dbPath;
    }

    await this.sendMessageAndWait({
      method: 'tools/call',
      params: {
        name: 'search_similar',
        arguments: baseArgs
      }
    });

    // 4. date_filter テスト - 2022年以降
    console.log('\n--- date_filter テスト（2022年以降） ---');
    const dateFilterArgs = {
      query: 'テスト',
      top_k: 5,
      date_filter: {
        from: '2022-01-01 00:00:00'
      }
    };
    if (this.dbPath) {
      dateFilterArgs.db_path = this.dbPath;
    }

    await this.sendMessageAndWait({
      method: 'tools/call',
      params: {
        name: 'search_similar',
        arguments: dateFilterArgs
      }
    });

    // 5. date_filter テスト - 2023年以降
    console.log('\n--- date_filter テスト（2023年以降） ---');
    const dateFilter2023Args = {
      query: 'テスト',
      top_k: 5,
      date_filter: {
        from: '2023-01-01 00:00:00'
      }
    };
    if (this.dbPath) {
      dateFilter2023Args.db_path = this.dbPath;
    }

    await this.sendMessageAndWait({
      method: 'tools/call',
      params: {
        name: 'search_similar',
        arguments: dateFilter2023Args
      }
    });

    // 6. date_filter テスト - 短期間
    console.log('\n--- date_filter テスト（短期間：2024年7月） ---');
    const shortPeriodArgs = {
      query: 'テスト',
      top_k: 5,
      date_filter: {
        from: '2024-07-01 00:00:00',
        to: '2024-07-31 23:59:59'
      }
    };
    if (this.dbPath) {
      shortPeriodArgs.db_path = this.dbPath;
    }

    await this.sendMessageAndWait({
      method: 'tools/call',
      params: {
        name: 'search_similar',
        arguments: shortPeriodArgs
      }
    });
  }

  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  stop() {
    if (this.serverProcess) {
      console.log('サーバープロセスを終了中...');
      this.serverProcess.stdin.end();
      this.serverProcess.kill('SIGTERM');
      
      // 強制終了のバックアップ
      setTimeout(() => {
        if (!this.serverProcess.killed) {
          console.log('強制終了します...');
          this.serverProcess.kill('SIGKILL');
        }
      }, 1000);
    }
  }

  setTestMode(mode) {
    this.testMode = mode;
  }
}

const { dbPath, websocketUrl, testMode, help } = parseTestArgs();

if (help) {
  showTestHelp();
  process.exit(0);
}

// Ctrl+C でクリーンアップ
process.on('SIGINT', () => {
  console.log('\nプログラムを終了します...');
  process.exit(0);
});

const client = new TwilogTestClient(dbPath, websocketUrl);
if (testMode) {
  client.setTestMode(testMode);
}
client.start().catch(console.error);
