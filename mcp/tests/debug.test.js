#!/usr/bin/env node

import { test, describe, before, after } from 'node:test';
import assert from 'node:assert';
import { initializeSharedServer, cleanupSharedServer, getSharedClient, parseTestArgs } from './base-client.js';

const { dbPath, websocketUrl } = parseTestArgs();

describe('デバッグテスト', () => {
  before(async () => {
    await initializeSharedServer({ dbPath, websocketUrl });
  });

  after(async () => {
    await cleanupSharedServer();
  });

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