#!/usr/bin/env node

import { test, describe, before, after } from 'node:test';
import assert from 'node:assert';
import { initializeSharedServer, cleanupSharedServer, getSharedClient, parseTestArgs } from './base-client.js';
import { runWebSocketDirectTests } from './websocket-direct.test.js';


const { dbPath, websocketUrl } = parseTestArgs();

// WebSocket直接通信テスト（MCPサーバー起動前）
describe('WebSocket直接通信テスト', () => {
  test('WebSocket直接通信の性能とプロトコル検証', async () => {
    const result = await runWebSocketDirectTests();
    assert.ok(result.success, 'WebSocket直接通信テストが成功');
    assert.ok(result.tests.length === 5, '5つのテストが実行された');
    
    // 各テスト結果の検証
    assert.ok(result.results.status.success, 'サーバー状態確認が成功');
    assert.ok(result.results.small.success, '小規模検索が成功');
    assert.ok(result.results.medium.success, '中規模検索が成功');
    assert.ok(result.results.large.success, '大規模検索が成功');
    assert.ok(result.results.chunked.success, '分割送信テストが成功');
  });
});

describe('全テストスイート', () => {
  before(async () => {
    await initializeSharedServer({ dbPath, websocketUrl });
  });

  after(async () => {
    await cleanupSharedServer();
  });

  describe('基本機能テスト', () => {
    test('サーバー状態確認', async () => {
      const client = getSharedClient();
      const result = await client.callTool('get_status');
      assert.ok(result, 'サーバー状態の取得に成功');
    });

    test('データベース統計取得', async () => {
      const client = getSharedClient();
      const result = await client.callTool('get_database_stats');
      assert.ok(result, 'データベース統計の取得に成功');
    });

    test('ツール一覧取得', async () => {
      const client = getSharedClient();
      const result = await client.listTools();
      assert.ok(result.tools, 'ツール一覧の取得に成功');
      assert.ok(result.tools.length > 0, 'ツールが存在する');
    });
  });

  describe('date_filterテスト', () => {
    test('基本検索（フィルターなし）', async () => {
      const client = getSharedClient();
      const args = {
        query: 'テスト',
        top_k: 5
      };
      
      const result = await client.callTool('search_similar', args);
      assert.ok(result, '基本検索が成功');
    });

    test('2022年以降のフィルター', async () => {
      const client = getSharedClient();
      const args = {
        query: 'テスト',
        top_k: 5,
        date_filter: {
          from: '2022-01-01 00:00:00'
        }
      };
      
      const result = await client.callTool('search_similar', args);
      assert.ok(result, '2022年以降のフィルターが成功');
    });

    test('2023年以降のフィルター', async () => {
      const client = getSharedClient();
      const args = {
        query: 'テスト',
        top_k: 5,
        date_filter: {
          from: '2023-01-01 00:00:00'
        }
      };
      
      const result = await client.callTool('search_similar', args);
      assert.ok(result, '2023年以降のフィルターが成功');
    });

    test('短期間フィルター（2024年7月）', async () => {
      const client = getSharedClient();
      const args = {
        query: 'テスト',
        top_k: 5,
        date_filter: {
          from: '2024-07-01 00:00:00',
          to: '2024-07-31 23:59:59'
        }
      };
      
      const result = await client.callTool('search_similar', args);
      assert.ok(result, '短期間フィルターが成功');
    });
  });

  describe('デバッグテスト', () => {
    test('短期間date_filterテスト', async () => {
      const client = getSharedClient();
      const args = {
        query: 'テスト',
        top_k: 3,
        date_filter: {
          from: '2024-07-01 00:00:00',
          to: '2024-07-07 23:59:59'
        }
      };
      
      const result = await client.callTool('search_similar', args);
      assert.ok(result, '短期間date_filterテストが成功');
    });
  });
});
