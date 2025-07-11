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
      
      const messageHandler = (data) => {
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
            
            // embed_client.pyと同じ判定ロジック
            const more = response.more;
            if (more === undefined) {
              // moreフィールドがない場合は単一レスポンス
              if (allResults.length > 0) {
                // 既にストリーミングデータがある場合はエラー
                const elapsed = Date.now() - startTime;
                resolve({ error: "サーバーからのレスポンスに'more'フィールドがありません", elapsed });
                return;
              } else {
                // 単一レスポンス
                const elapsed = Date.now() - startTime;
                resolve({ 
                  success: true, 
                  data: result, 
                  elapsed 
                });
                return;
              }
            } else {
              // Streaming Extensions形式
              isStreamingMode = true;
              chunkCount++;
              
              // resultの形式に応じて処理
              if (result && typeof result === 'object' && 'data' in result && Array.isArray(result.data)) {
                allResults.push(...result.data);
              } else if (Array.isArray(result)) {
                allResults.push(...result);
              } else {
                allResults.push(result);
              }
              
              // 最後のチャンクかチェック
              if (more === false) {
                const elapsed = Date.now() - startTime;
                resolve({ 
                  success: true, 
                  data: allResults, 
                  elapsed, 
                  chunks: chunkCount 
                });
                return;
              }
            }
          } else {
            const elapsed = Date.now() - startTime;
            resolve({ error: 'サーバーがJSON-RPC 2.0形式に対応していません', elapsed });
          }
        } catch (error) {
          const elapsed = Date.now() - startTime;
          ws.removeListener('message', messageHandler);
          resolve({ error: `レスポンス解析エラー: ${error.message}`, elapsed });
        }
      };
      
      ws.on('message', messageHandler);

      // タイムアウト設定（10秒）
      const timeoutId = setTimeout(() => {
        const elapsed = Date.now() - startTime;
        ws.removeListener('message', messageHandler);
        resolve({ error: `タイムアウト（10秒）`, elapsed });
      }, 10000);
      
      // 正常終了時にタイムアウトをクリアしリスナーを削除
      const originalResolve = resolve;
      resolve = (result) => {
        clearTimeout(timeoutId);
        ws.removeListener('message', messageHandler);
        originalResolve(result);
      };

      ws.send(JSON.stringify(request));
    });
  }
}

// 個別テスト関数群
async function setupWebSocketConnection() {
  const tester = new WebSocketDirectTest();
  const ws = await tester.connectWebSocket();
  return { tester, ws };
}

function cleanupConnection(ws) {
  if (ws && ws.readyState === ws.OPEN) {
    ws.close();
  }
}

test('サーバー状態確認テスト', async () => {
  const { tester, ws } = await setupWebSocketConnection();
  
  try {
    console.log('サーバー状態確認テスト開始...');
    const statusResult = await tester.sendRequest(ws, 'get_status');
    console.log(`結果: ${statusResult.success ? '成功' : '失敗'} (${statusResult.elapsed}ms)`);
    console.log(`サーバー状態: ${statusResult.data?.status || 'unknown'}`);
    
    assert.ok(statusResult.success, 'get_status が成功');
    assert.ok(statusResult.elapsed < 1000, `レスポンス時間が1秒未満: ${statusResult.elapsed}ms`);
    assert.ok(statusResult.data.status === 'running', 'サーバーが稼働中');
  } finally {
    cleanupConnection(ws);
  }
});

test('小規模検索テスト (5件)', async () => {
  const { tester, ws } = await setupWebSocketConnection();
  
  try {
    console.log('小規模検索テスト (5件) 開始...');
    const smallResult = await tester.sendRequest(ws, 'search_similar', { 
      query: 'テスト', 
      settings: { top_k: 5 }
    });
    console.log(`結果: ${smallResult.success ? '成功' : '失敗'} (${smallResult.elapsed}ms)`);
    console.log(`取得件数: ${smallResult.data?.length || 0}件`);
    
    assert.ok(smallResult.success, 'search_similar(5件) が成功');
    assert.ok(smallResult.elapsed < 5000, `レスポンス時間が5秒未満: ${smallResult.elapsed}ms`);
    assert.strictEqual(smallResult.data.length, 5, '正確に5件取得');
  } finally {
    cleanupConnection(ws);
  }
});

test('中規模検索テスト (100件)', async () => {
  const { tester, ws } = await setupWebSocketConnection();
  
  try {
    console.log('中規模検索テスト (100件) 開始...');
    const mediumResult = await tester.sendRequest(ws, 'search_similar', { 
      query: 'テスト', 
      settings: { top_k: 100 }
    });
    console.log(`結果: ${mediumResult.success ? '成功' : '失敗'} (${mediumResult.elapsed}ms)`);
    console.log(`取得件数: ${mediumResult.data?.length || 0}件`);
    
    assert.ok(mediumResult.success, 'search_similar(100件) が成功');
    assert.ok(mediumResult.elapsed < 5000, `レスポンス時間が5秒未満: ${mediumResult.elapsed}ms`);
    assert.strictEqual(mediumResult.data.length, 100, '正確に100件取得');
  } finally {
    cleanupConnection(ws);
  }
});

test('大規模検索テスト (1000件)', async () => {
  const { tester, ws } = await setupWebSocketConnection();
  
  try {
    console.log('大規模検索テスト (1000件) 開始...');
    const largeResult = await tester.sendRequest(ws, 'search_similar', { 
      query: 'テスト', 
      settings: { top_k: 1000 }
    });
    console.log(`結果: ${largeResult.success ? '成功' : '失敗'} (${largeResult.elapsed}ms)`);
    console.log(`取得件数: ${largeResult.data?.length || 0}件`);
    
    assert.ok(largeResult.success, 'search_similar(1000件) が成功');
    assert.ok(largeResult.elapsed < 5000, `レスポンス時間が5秒未満: ${largeResult.elapsed}ms`);
    assert.strictEqual(largeResult.data.length, 1000, '正確に1000件取得');
  } finally {
    cleanupConnection(ws);
  }
});

test('分割送信テスト (50000件)', async () => {
  const { tester, ws } = await setupWebSocketConnection();
  
  try {
    console.log('分割送信テスト (50000件) 開始...');
    const chunkResult = await tester.sendRequest(ws, 'search_similar', { 
      query: 'テスト', 
      settings: { top_k: 50000 }
    });
    console.log(`結果: ${chunkResult.success ? '成功' : '失敗'} (${chunkResult.elapsed}ms)`);
    console.log(`取得件数: ${chunkResult.data?.length || 0}件`);
    
    assert.ok(chunkResult.success, 'search_similar(50000件) が成功');
    assert.ok(chunkResult.elapsed < 10000, `レスポンス時間が10秒未満: ${chunkResult.elapsed}ms`);
    assert.ok(chunkResult.data.length > 10000, `大量のデータ取得: ${chunkResult.data.length}件`);
  } finally {
    cleanupConnection(ws);
  }
});

// エクスポート用のテスト関数（後方互換性のため残す）
export async function runWebSocketDirectTests() {
  // 個別テストが実行されるため、この関数は空にする
  return { success: true, message: '個別テストを実行してください' };
}