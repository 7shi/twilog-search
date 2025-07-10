#!/usr/bin/env node

import { test, describe } from 'node:test';
import assert from 'node:assert';
import { TwilogFilters } from '../dist/filters.js';

describe('ユニットテスト', () => {
  describe('TwilogFilters.applyDateFilter', () => {
    // テスト用のサンプルデータ
    const samplePosts = [
      {
        user: 'user1',
        content: 'テスト投稿1',
        timestamp: '2021-12-31 23:59:59',
        url: 'https://example.com/1'
      },
      {
        user: 'user2',
        content: 'テスト投稿2',
        timestamp: '2022-01-01 00:00:00',
        url: 'https://example.com/2'
      },
      {
        user: 'user3',
        content: 'テスト投稿3',
        timestamp: '2022-06-15 12:00:00',
        url: 'https://example.com/3'
      },
      {
        user: 'user4',
        content: 'テスト投稿4',
        timestamp: '2023-01-01 00:00:00',
        url: 'https://example.com/4'
      }
    ];

    test('from日付フィルターの基本動作', () => {
      const dateFilter = {
        from: '2022-01-01 00:00:00'
      };

      const filteredPosts = TwilogFilters.applyDateFilter(samplePosts, dateFilter);
      
      // 期待値: 2022-01-01 00:00:00 以降の投稿のみ（user2, user3, user4）
      assert.strictEqual(filteredPosts.length, 3, '2022年以降の投稿が3件');
      assert.strictEqual(filteredPosts[0].user, 'user2', '最初の投稿がuser2');
      assert.strictEqual(filteredPosts[1].user, 'user3', '2番目の投稿がuser3');
      assert.strictEqual(filteredPosts[2].user, 'user4', '3番目の投稿がuser4');
    });

    test('to日付フィルターの基本動作', () => {
      const dateFilter = {
        to: '2022-12-31 23:59:59'
      };

      const filteredPosts = TwilogFilters.applyDateFilter(samplePosts, dateFilter);
      
      // 期待値: 2022年末まで（user1, user2, user3）
      assert.strictEqual(filteredPosts.length, 3, '2022年末までの投稿が3件');
      assert.strictEqual(filteredPosts[0].user, 'user1', '最初の投稿がuser1');
      assert.strictEqual(filteredPosts[1].user, 'user2', '2番目の投稿がuser2');
      assert.strictEqual(filteredPosts[2].user, 'user3', '3番目の投稿がuser3');
    });

    test('from-to範囲フィルターの基本動作', () => {
      const dateFilter = {
        from: '2022-01-01 00:00:00',
        to: '2022-12-31 23:59:59'
      };

      const filteredPosts = TwilogFilters.applyDateFilter(samplePosts, dateFilter);
      
      // 期待値: 2022年の投稿のみ（user2, user3）
      assert.strictEqual(filteredPosts.length, 2, '2022年の投稿が2件');
      assert.strictEqual(filteredPosts[0].user, 'user2', '最初の投稿がuser2');
      assert.strictEqual(filteredPosts[1].user, 'user3', '2番目の投稿がuser3');
    });

    test('異なる日付形式の対応', () => {
      const dateFormats = [
        '2022-01-01',
        '2022-01-01 12:00:00',
        '2022-01-01T12:00:00',
        '2022-01-01T12:00:00Z'
      ];

      dateFormats.forEach(format => {
        const testFilter = { from: format };
        
        // エラーが発生せず、結果が返されることを確認
        assert.doesNotThrow(() => {
          const result = TwilogFilters.applyDateFilter(samplePosts, testFilter);
          assert.ok(Array.isArray(result), `形式"${format}"で配列が返される`);
        }, `日付形式"${format}"が正常に処理される`);
      });
    });

    test('空の投稿配列での動作', () => {
      const dateFilter = {
        from: '2022-01-01 00:00:00'
      };

      const filteredPosts = TwilogFilters.applyDateFilter([], dateFilter);
      
      assert.strictEqual(filteredPosts.length, 0, '空の配列は空の配列を返す');
    });

    test('フィルター条件なしでの動作', () => {
      const filteredPosts = TwilogFilters.applyDateFilter(samplePosts, {});
      
      assert.strictEqual(filteredPosts.length, samplePosts.length, 'フィルター条件なしで全投稿を返す');
    });
  });
});