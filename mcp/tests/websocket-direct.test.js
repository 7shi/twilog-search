// WebSocket直接接続でのテスト関数群
// all.test.jsから呼び出される独立したテスト関数

import { test, describe } from 'node:test';
import assert from 'node:assert';
import WebSocket from 'ws';

class WebSocketDirectTest {
  constructor(url = 'ws://localhost:8765') {
    this.url = url;
    this.requestId = 1;
  }

  async connectWebSocket() {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.url);
      let timeoutId;
      
      const cleanup = () => {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }
      };
      
      ws.on('open', () => {
        cleanup();
        resolve(ws);
      });

      ws.on('error', (error) => {
        cleanup();
        if (error.message.includes('ECONNREFUSED')) {
          reject(new Error('サーバーが起動していません'));
        } else {
          reject(new Error(`WebSocket接続エラー: ${error.message}`));
        }
      });

      timeoutId = setTimeout(() => {
        ws.terminate();
        reject(new Error('WebSocket接続タイムアウト（5秒）'));
      }, 5000);
    });
  }

  async sendRequest(ws, method, params = {}) {
    const startTime = Date.now();
    const requestId = this.requestId++;
    
    const request = {
      jsonrpc: "2.0",
      method,
      params,
      id: requestId
    };

    return new Promise((resolve, reject) => {
      let allResults = [];
      let isStreamingMode = false;
      let chunkCount = 0;
      
      ws.on('message', (data) => {
        try {
          const response = JSON.parse(data.toString());
          
          if (response.id !== requestId) {
            return; // 他のリクエストのレスポンス
          }
          
          if (response.jsonrpc === "2.0") {
            if (response.error) {
              const elapsed = Date.now() - startTime;
              resolve({ error: response.error.message, elapsed });
              return;
            }
            
            const result = response.result;
            
            // Streaming Extensions形式の処理
            if (result && typeof result === 'object') {
              if ('data' in result && Array.isArray(result.data)) {
                isStreamingMode = true;
                chunkCount++;
                allResults.push(...result.data);
                
                // moreフィールドはresponseのトップレベルに存在（embed_server.py仕様）
                if (response.more === false || response.more === undefined) {
                  const elapsed = Date.now() - startTime;
                  resolve({ 
                    success: true, 
                    data: allResults, 
                    elapsed, 
                    chunks: chunkCount 
                  });
                  return;
                }
              } else if (Array.isArray(result)) {
                // embed_server.pyの分割送信形式（各要素を個別メッセージとして送信）
                isStreamingMode = true;
                chunkCount++;
                allResults.push(result);
                
                // moreフィールドで継続判定
                if (response.more === false || response.more === undefined) {
                  const elapsed = Date.now() - startTime;
                  resolve({ 
                    success: true, 
                    data: allResults, 
                    elapsed, 
                    chunks: chunkCount 
                  });
                  return;
                }
              } else if (!isStreamingMode) {
                // 単一レスポンス
                const elapsed = Date.now() - startTime;
                resolve({ 
                  success: true, 
                  data: result, 
                  elapsed 
                });
                return;
              }
            } else if (!isStreamingMode) {
              // プリミティブ型レスポンス
              const elapsed = Date.now() - startTime;
              resolve({ 
                success: true, 
                data: result, 
                elapsed 
              });
              return;
            }
          } else {
            const elapsed = Date.now() - startTime;
            resolve({ error: 'サーバーがJSON-RPC 2.0形式に対応していません', elapsed });
          }
        } catch (error) {
          const elapsed = Date.now() - startTime;
          resolve({ error: `レスポンス解析エラー: ${error.message}`, elapsed });
        }
      });

      // タイムアウト設定（30秒）
      setTimeout(() => {
        const elapsed = Date.now() - startTime;
        resolve({ error: `タイムアウト（30秒）`, elapsed });
      }, 30000);

      ws.send(JSON.stringify(request));
    });
  }
}

// エクスポート用のテスト関数
export async function runWebSocketDirectTests() {
  let tester;
  let ws;

  try {
    // WebSocket接続
    tester = new WebSocketDirectTest();
    ws = await tester.connectWebSocket();
    
    // サーバー状態確認テスト
    const statusResult = await tester.sendRequest(ws, 'get_status');
    assert.ok(statusResult.success, 'get_status が成功');
    assert.ok(statusResult.elapsed < 1000, `レスポンス時間が1秒未満: ${statusResult.elapsed}ms`);
    assert.ok(statusResult.data.status === 'running', 'サーバーが稼働中');

    // 小規模検索テスト (10件)
    const smallResult = await tester.sendRequest(ws, 'search_similar', { 
      query: 'テスト', 
      top_k: 10 
    });
    assert.ok(smallResult.success, 'search_similar(10件) が成功');
    assert.ok(smallResult.elapsed < 5000, `レスポンス時間が5秒未満: ${smallResult.elapsed}ms`);
    assert.strictEqual(smallResult.data.length, 10, '正確に10件取得');

    // 中規模検索テスト (100件)
    const mediumResult = await tester.sendRequest(ws, 'search_similar', { 
      query: 'テスト', 
      top_k: 100 
    });
    assert.ok(mediumResult.success, 'search_similar(100件) が成功');
    assert.ok(mediumResult.elapsed < 5000, `レスポンス時間が5秒未満: ${mediumResult.elapsed}ms`);
    assert.strictEqual(mediumResult.data.length, 100, '正確に100件取得');

    // 大規模検索テスト (1000件)
    const largeResult = await tester.sendRequest(ws, 'search_similar', { 
      query: 'テスト', 
      top_k: 1000 
    });
    assert.ok(largeResult.success, 'search_similar(1000件) が成功');
    assert.ok(largeResult.elapsed < 5000, `レスポンス時間が5秒未満: ${largeResult.elapsed}ms`);
    assert.strictEqual(largeResult.data.length, 1000, '正確に1000件取得');

    // 分割送信テスト（適度なサイズ）
    const chunkResult = await tester.sendRequest(ws, 'search_similar', { 
      query: 'テスト', 
      top_k: 50000 // 全件ではなく適度なサイズで分割送信をテスト
    });
    assert.ok(chunkResult.success, 'search_similar(50000件) が成功');
    assert.ok(chunkResult.elapsed < 10000, `レスポンス時間が10秒未満: ${chunkResult.elapsed}ms`);
    assert.ok(chunkResult.data.length > 10000, `大量のデータ取得: ${chunkResult.data.length}件`);
    
    return {
      success: true,
      tests: ['status', 'small', 'medium', 'large', 'chunked'],
      results: {
        status: statusResult,
        small: smallResult,
        medium: mediumResult,
        large: largeResult,
        chunked: chunkResult
      }
    };
  } finally {
    if (ws) {
      ws.close();
    }
  }
}