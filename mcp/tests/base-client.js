#!/usr/bin/env node

import { spawn } from 'child_process';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

/**
 * MCP SDKを使用したテストヘルパー
 * JSON RPC通信とレスポンス処理を統一
 */
export class MCPTestClient {
  constructor(dbPath, websocketUrl, clientName = 'test-client') {
    this.dbPath = dbPath;
    this.websocketUrl = websocketUrl;
    this.clientName = clientName;
    this.client = null;
    this.transport = null;
    this.serverProcess = null;
  }

  async start() {
    console.log('MCPサーバーを起動中...');
    if (this.dbPath) {
      console.log(`データベース: ${this.dbPath}`);
    }
    if (this.websocketUrl) {
      console.log(`WebSocket URL: ${this.websocketUrl}`);
    }
    
    const args = this.buildServerArgs();

    // MCP SDKのクライアントを初期化
    this.transport = new StdioClientTransport({
      command: 'npm',
      args: args
    });

    this.client = new Client({
      name: this.clientName,
      version: '1.0.0'
    }, {
      capabilities: {
        tools: {}
      }
    });

    // 接続
    await this.client.connect(this.transport);
  }

  buildServerArgs() {
    const args = ['start'];
    if (this.dbPath || this.websocketUrl) {
      args.push('--');
      if (this.dbPath) {
        args.push('--db', this.dbPath);
      }
      if (this.websocketUrl) {
        args.push('--websocket', this.websocketUrl);
      }
    }
    return args;
  }

  async callTool(name, args = {}) {
    try {
      const result = await this.client.callTool({ name, arguments: args });
      console.log(`ツール ${name} 結果:`, JSON.stringify(result, null, 2));
      return result;
    } catch (error) {
      console.error(`ツール ${name} エラー:`, error);
      throw error;
    }
  }

  async listTools() {
    try {
      const result = await this.client.listTools();
      console.log('利用可能なツール:', JSON.stringify(result, null, 2));
      return result;
    } catch (error) {
      console.error('ツール一覧取得エラー:', error);
      throw error;
    }
  }

  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async stop() {
    if (this.client) {
      await this.client.close();
    }
    if (this.serverProcess) {
      this.serverProcess.kill();
    }
  }
}

/**
 * 共有サーバー管理クラス
 */
class SharedMCPServer {
  constructor() {
    this.client = null;
    this.isInitialized = false;
  }

  async initialize(dbPath, websocketUrl) {
    if (this.isInitialized) {
      return this.client;
    }

    console.log('=== 共有MCPサーバー初期化中 ===');
    this.client = new MCPTestClient(dbPath, websocketUrl, 'shared-test-client');
    await this.client.start();
    this.isInitialized = true;
    console.log('=== 共有MCPサーバー初期化完了 ===\n');
    
    return this.client;
  }

  async cleanup() {
    if (this.client) {
      console.log('\n=== 共有MCPサーバー終了中 ===');
      await this.client.stop();
      this.client = null;
      this.isInitialized = false;
      console.log('=== 共有MCPサーバー終了完了 ===');
    }
  }

  getClient() {
    if (!this.isInitialized || !this.client) {
      throw new Error('共有サーバーが初期化されていません');
    }
    return this.client;
  }
}

// グローバル共有サーバーインスタンス
const sharedServer = new SharedMCPServer();

/**
 * 共有サーバーを初期化（テストスイート開始時に呼び出し）
 */
export async function initializeSharedServer(options = {}) {
  return await sharedServer.initialize(options.dbPath, options.websocketUrl);
}

/**
 * 共有サーバーを終了（テストスイート終了時に呼び出し）
 */
export async function cleanupSharedServer() {
  await sharedServer.cleanup();
}

/**
 * 共有サーバーのクライアントを取得
 */
export function getSharedClient() {
  return sharedServer.getClient();
}

/**
 * テストランナー関数（個別サーバー起動版 - 後方互換性のため残存）
 */
export async function runMCPTest(testName, testFunction, options = {}) {
  console.log(`\n=== ${testName} 開始 ===`);
  
  const client = new MCPTestClient(
    options.dbPath, 
    options.websocketUrl, 
    options.clientName || testName
  );
  
  try {
    await client.start();
    await testFunction(client);
    console.log(`=== ${testName} 完了 ===`);
  } catch (error) {
    console.error(`=== ${testName} エラー ===`, error);
    throw error;
  } finally {
    await client.stop();
  }
}

// コマンドライン引数の解析
export function parseTestArgs() {
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
    } else if (arg.startsWith('--db=')) {
      result.dbPath = arg.split('=')[1];
    } else if (arg.startsWith('--websocket=')) {
      result.websocketUrl = arg.split('=')[1];
    }
  }

  return result;
}

// Ctrl+C でクリーンアップ
process.on('SIGINT', () => {
  console.log('\nプログラムを終了します...');
  process.exit(0);
});