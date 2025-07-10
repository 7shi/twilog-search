#!/usr/bin/env node

import { test, describe, before, after } from 'node:test';
import assert from 'node:assert';
import { initializeSharedServer, cleanupSharedServer, getSharedClient, parseTestArgs } from './base-client.js';

const { dbPath, websocketUrl } = parseTestArgs();

describe('date_filterテスト', () => {
  before(async () => {
    await initializeSharedServer({ dbPath, websocketUrl });
  });

  after(async () => {
    await cleanupSharedServer();
  });

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