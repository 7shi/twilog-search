#!/usr/bin/env node

import { test, describe, before, after } from 'node:test';
import assert from 'node:assert';
import { initializeSharedServer, cleanupSharedServer, getSharedClient, parseTestArgs } from './base-client.js';

const { dbPath, websocketUrl } = parseTestArgs();

describe('基本機能テスト', () => {
  before(async () => {
    await initializeSharedServer({ dbPath, websocketUrl });
  });

  after(async () => {
    await cleanupSharedServer();
  });

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
