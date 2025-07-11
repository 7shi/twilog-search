// WebSocket直接通信のデバッグテスト
// 161行目の「正確に10件取得」失敗の原因を調査

import { test, describe } from 'node:test';
import assert from 'node:assert';
import WebSocket from 'ws';
import util from 'util';

class DebugWebSocketTest {
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
        console.log('✓ WebSocket接続成功');
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

  async sendDebugRequest(ws, method, params = {}) {
    const startTime = Date.now();
    const requestId = this.requestId++;
    
    const request = {
      jsonrpc: "2.0",
      method,
      params,
      id: requestId
    };

    console.log('\n=== リクエスト送信 ===');
    console.log('Method:', method);
    console.log('Params:', JSON.stringify(params, null, 2));
    console.log('Request ID:', requestId);

    return new Promise((resolve, reject) => {
      let allResults = [];
      let isStreamingMode = false;
      let chunkCount = 0;
      let rawMessages = [];
      
      const messageHandler = (data) => {
        try {
          const rawMessage = data.toString();
          rawMessages.push(rawMessage);
          
          console.log(`\n--- メッセージ受信 ${rawMessages.length} ---`);
          console.log('Raw message length:', rawMessage.length);
          console.log('Raw message (first 200 chars):', rawMessage.substring(0, 200));
          
          const response = JSON.parse(rawMessage);
          console.log('Parsed response keys:', Object.keys(response));
          console.log('Response/Request ID:', response.id, '/', requestId);
          
          if (response.id !== requestId) {
            console.log('⚠️  異なるリクエストIDのレスポンス - スキップ');
            return;
          }
          
          if (response.jsonrpc === "2.0") {
            if (response.error) {
              console.log('❌ エラーレスポンス:', response.error);
              const elapsed = Date.now() - startTime;
              resolve({ 
                error: response.error.message, 
                elapsed,
                rawMessages,
                debugInfo: {
                  totalMessages: rawMessages.length,
                  isStreamingMode,
                  chunkCount
                }
              });
              return;
            }
            
            const result = response.result;
            console.log('Result type:', typeof result);
            console.log('Result is array:', Array.isArray(result));
            
            // embed_client.pyと同じ判定ロジック
            const more = response.more;
            if (more === undefined) {
              // moreフィールドがない場合は単一レスポンス
              if (allResults.length > 0) {
                // 既にストリーミングデータがある場合はエラー
                const elapsed = Date.now() - startTime;
                resolve({ 
                  error: "サーバーからのレスポンスに'more'フィールドがありません", 
                  elapsed,
                  rawMessages,
                  debugInfo: {
                    totalMessages: rawMessages.length,
                    isStreamingMode,
                    chunkCount
                  }
                });
                return;
              } else {
                // 単一レスポンス
                console.log('📦 単一レスポンスモード');
                console.log('Result length:', Array.isArray(result) ? result.length : 'not array');
                
                if (Array.isArray(result) && result.length > 0) {
                  console.log('First item:', JSON.stringify(result[0], null, 2));
                  if (result.length > 1) {
                    console.log(`... 他${result.length - 1}件省略`);
                  }
                }
                
                const elapsed = Date.now() - startTime;
                resolve({ 
                  success: true, 
                  data: result, 
                  elapsed,
                  rawMessages,
                  debugInfo: {
                    totalMessages: rawMessages.length,
                    isStreamingMode,
                    chunkCount,
                    finalDataLength: Array.isArray(result) ? result.length : 'not array'
                  }
                });
                return;
              }
            } else {
              // Streaming Extensions形式
              console.log('🔄 ストリーミングモード検出');
              isStreamingMode = true;
              chunkCount++;
              console.log('Chunk', chunkCount);
              
              // resultの形式に応じて処理
              if (result && typeof result === 'object' && 'data' in result && Array.isArray(result.data)) {
                console.log('- data length:', result.data.length);
                if (result.data.length > 0) {
                  console.log('- first item:', JSON.stringify(result.data[0], null, 2));
                  if (result.data.length > 1) {
                    console.log(`- ... 他${result.data.length - 1}件省略`);
                  }
                }
                allResults.push(...result.data);
              } else if (Array.isArray(result)) {
                console.log('- result length:', result.length);
                if (result.length > 0) {
                  console.log('- first item:', JSON.stringify(result[0], null, 2));
                  if (result.length > 1) {
                    console.log(`- ... 他${result.length - 1}件省略`);
                  }
                }
                allResults.push(...result);
              } else {
                console.log('- single item');
                allResults.push(result);
              }
              
              console.log('累計結果数:', allResults.length);
              
              // 最後のチャンクかチェック
              if (more === false) {
                console.log('✓ ストリーミング終了');
                const elapsed = Date.now() - startTime;
                resolve({ 
                  success: true, 
                  data: allResults, 
                  elapsed, 
                  chunks: chunkCount,
                  rawMessages,
                  debugInfo: {
                    totalMessages: rawMessages.length,
                    isStreamingMode,
                    chunkCount,
                    finalDataLength: allResults.length
                  }
                });
                return;
              }
            }
          } else {
            console.log('❌ 非JSON-RPC 2.0レスポンス');
            const elapsed = Date.now() - startTime;
            resolve({ 
              error: 'サーバーがJSON-RPC 2.0形式に対応していません', 
              elapsed,
              rawMessages,
              debugInfo: {
                totalMessages: rawMessages.length,
                isStreamingMode,
                chunkCount
              }
            });
          }
        } catch (error) {
          console.log('❌ レスポンス解析エラー:', error.message);
          console.log('Raw message:', data.toString().substring(0, 1000));
          const elapsed = Date.now() - startTime;
          ws.removeListener('message', messageHandler);
          resolve({ 
            error: `レスポンス解析エラー: ${error.message}`, 
            elapsed,
            rawMessages,
            debugInfo: {
              totalMessages: rawMessages.length,
              isStreamingMode,
              chunkCount
            }
          });
        }
      };
      
      ws.on('message', messageHandler);

      // タイムアウト設定（10秒）
      const timeoutId = setTimeout(() => {
        console.log('⏰ タイムアウト発生');
        const elapsed = Date.now() - startTime;
        resolve({ 
          error: `タイムアウト（10秒）`, 
          elapsed,
          rawMessages,
          debugInfo: {
            totalMessages: rawMessages.length,
            isStreamingMode,
            chunkCount,
            finalDataLength: allResults.length
          }
        });
      }, 10000);
      
      // 正常終了時にタイムアウトをクリアしリスナーを削除
      const originalResolve = resolve;
      resolve = (result) => {
        clearTimeout(timeoutId);
        ws.removeListener('message', messageHandler);
        originalResolve(result);
      };

      console.log('📤 リクエスト送信中...');
      ws.send(JSON.stringify(request));
    });
  }
}

// 個別デバッグテスト関数群
async function setupDebugWebSocketConnection() {
  const tester = new DebugWebSocketTest();
  const ws = await tester.connectWebSocket();
  return { tester, ws };
}

function cleanupConnection(ws) {
  if (ws && ws.readyState === ws.OPEN) {
    ws.close();
  }
}

test('デバッグ: サーバー状態確認', async () => {
  const { tester, ws } = await setupDebugWebSocketConnection();
  
  try {
    console.log('📊 サーバー状態確認テスト');
    const statusResult = await tester.sendDebugRequest(ws, 'get_status');
    console.log('Status result:', JSON.stringify(statusResult, null, 2));
    
    assert.ok(statusResult.success, 'サーバー状態確認が成功');
    assert.ok(statusResult.data, 'ステータスデータが存在');
  } finally {
    cleanupConnection(ws);
  }
});

test('デバッグ: 5件検索テスト', async () => {
  const { tester, ws } = await setupDebugWebSocketConnection();
  
  try {
    console.log('🔍 5件検索テスト');
    const result = await tester.sendDebugRequest(ws, 'search_similar', { 
      query: 'テスト', 
      settings: { top_k: 5 }
    });
    
    console.log('=== 5件検索結果分析 ===');
    console.log('Success:', result.success);
    console.log('Data length:', Array.isArray(result.data) ? result.data.length : 'not array');
    console.log('Expected: 5');
    console.log('Match:', Array.isArray(result.data) && result.data.length === 5);
    
    assert.ok(result.success, '5件検索が成功');
    assert.ok(Array.isArray(result.data), 'データが配列');
    assert.strictEqual(result.data.length, 5, '正確に5件取得');
  } finally {
    cleanupConnection(ws);
  }
});

test('デバッグ: 10件検索テスト（settings形式）', async () => {
  const { tester, ws } = await setupDebugWebSocketConnection();
  
  try {
    console.log('🎯 10件検索テスト（settings形式）');
    const result = await tester.sendDebugRequest(ws, 'search_similar', { 
      query: 'テスト', 
      settings: { top_k: 10 }
    });
    
    console.log('=== 10件検索結果分析 ===');
    console.log('Success:', result.success);
    console.log('Error:', result.error);
    console.log('Elapsed:', result.elapsed, 'ms');
    console.log('Data type:', typeof result.data);
    console.log('Data is array:', Array.isArray(result.data));
    
    if (Array.isArray(result.data)) {
      console.log('実際の件数:', result.data.length);
      console.log('期待件数: 10');
      console.log('件数一致:', result.data.length === 10);
      
      if (result.data.length > 0) {
        console.log('最初の項目:', JSON.stringify(result.data[0], null, 2));
      }
      if (result.data.length > 1) {
        console.log('最後の項目:', JSON.stringify(result.data[result.data.length - 1], null, 2));
      }
    } else {
      console.log('❌ データが配列ではありません');
      console.log('Data:', result.data);
    }
    
    console.log('Debug info:', JSON.stringify(result.debugInfo, null, 2));
    console.log('Raw messages count:', result.rawMessages ? result.rawMessages.length : 0);
    
    if (result.rawMessages && result.rawMessages.length > 0) {
      console.log('\n=== 生メッセージ分析 ===');
      result.rawMessages.forEach((msg, index) => {
        console.log(`Message ${index + 1}:`);
        console.log('  Length:', msg.length);
        console.log('  First 200 chars:', msg.substring(0, 200));
        try {
          const parsed = JSON.parse(msg);
          console.log('  Parsed keys:', Object.keys(parsed));
          if (parsed.result && typeof parsed.result === 'object') {
            console.log('  Result keys:', Object.keys(parsed.result));
            if (parsed.result.data && Array.isArray(parsed.result.data)) {
              console.log('  Data length:', parsed.result.data.length);
            }
          }
        } catch (e) {
          console.log('  Parse error:', e.message);
        }
      });
    }
    
    assert.ok(result.success, '10件検索が成功');
    assert.ok(Array.isArray(result.data), 'データが配列');
    assert.strictEqual(result.data.length, 10, '正確に10件取得');
  } finally {
    cleanupConnection(ws);
  }
});

test('デバッグ: 20件検索テスト', async () => {
  const { tester, ws } = await setupDebugWebSocketConnection();
  
  try {
    console.log('🔍 20件検索テスト');
    const result = await tester.sendDebugRequest(ws, 'search_similar', { 
      query: 'テスト', 
      settings: { top_k: 20 }
    });
    
    console.log('=== 20件検索結果分析 ===');
    console.log('Success:', result.success);
    console.log('Data length:', Array.isArray(result.data) ? result.data.length : 'not array');
    console.log('Expected: 20');
    console.log('Match:', Array.isArray(result.data) && result.data.length === 20);
    
    assert.ok(result.success, '20件検索が成功');
    assert.ok(Array.isArray(result.data), 'データが配列');
    assert.strictEqual(result.data.length, 20, '正確に20件取得');
  } finally {
    cleanupConnection(ws);
  }
});

// デバッグテストの実行（後方互換性のため残す）
export async function runDebugWebSocketTests() {
  return { success: true, message: '個別デバッグテストを実行してください' };
}

// 単体実行用の条件は削除（個別テストが実行されるため）