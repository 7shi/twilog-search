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
      
      ws.on('message', (data) => {
        try {
          const rawMessage = data.toString();
          rawMessages.push(rawMessage);
          
          console.log(`\n--- メッセージ受信 ${rawMessages.length} ---`);
          console.log('Raw message length:', rawMessage.length);
          console.log('Raw message (first 500 chars):', rawMessage.substring(0, 500));
          
          const response = JSON.parse(rawMessage);
          console.log('Parsed response keys:', Object.keys(response));
          console.log('Response ID:', response.id);
          console.log('Request ID:', requestId);
          
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
            
            if (result && typeof result === 'object') {
              console.log('Result keys:', Object.keys(result));
              
              if ('data' in result && Array.isArray(result.data)) {
                console.log('🔄 ストリーミングモード検出');
                isStreamingMode = true;
                chunkCount++;
                console.log('Chunk', chunkCount, '- data length:', result.data.length);
                console.log('First item in chunk:', result.data[0] ? JSON.stringify(result.data[0], null, 2) : 'null');
                
                allResults.push(...result.data);
                console.log('累計結果数:', allResults.length);
                
                // moreフィールドの確認
                console.log('response.more:', response.more);
                console.log('result.more:', result.more);
                
                if (response.more === false || response.more === undefined) {
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
              } else if (Array.isArray(result)) {
                // embed_server.pyの分割送信形式を検出
                console.log('🔄 分割送信モード検出');
                isStreamingMode = true;
                chunkCount++;
                console.log('Chunk', chunkCount, '- result type:', typeof result);
                console.log('Result:', JSON.stringify(result, null, 2));
                
                // 各要素を個別のメッセージとして処理
                allResults.push(result);
                console.log('累計結果数:', allResults.length);
                
                // moreフィールドの確認
                console.log('response.more:', response.more);
                
                if (response.more === false || response.more === undefined) {
                  console.log('✓ 分割送信終了');
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
              } else if (!isStreamingMode) {
                console.log('📦 単一レスポンスモード');
                console.log('Result length:', Array.isArray(result) ? result.length : 'not array');
                
                if (Array.isArray(result)) {
                  console.log('First item:', JSON.stringify(result[0], null, 2));
                  console.log('Last item:', JSON.stringify(result[result.length - 1], null, 2));
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
            } else if (!isStreamingMode) {
              console.log('🔤 プリミティブ型レスポンス');
              console.log('Result value:', result);
              
              const elapsed = Date.now() - startTime;
              resolve({ 
                success: true, 
                data: result, 
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
      });

      // タイムアウト設定（30秒）
      setTimeout(() => {
        console.log('⏰ タイムアウト発生');
        const elapsed = Date.now() - startTime;
        resolve({ 
          error: `タイムアウト（30秒）`, 
          elapsed,
          rawMessages,
          debugInfo: {
            totalMessages: rawMessages.length,
            isStreamingMode,
            chunkCount,
            finalDataLength: allResults.length
          }
        });
      }, 30000);

      console.log('📤 リクエスト送信中...');
      ws.send(JSON.stringify(request));
    });
  }
}

// デバッグテストの実行
export async function runDebugWebSocketTests() {
  console.log('🔍 WebSocket直接通信デバッグテスト開始');
  
  let tester;
  let ws;

  try {
    // WebSocket接続
    tester = new DebugWebSocketTest();
    ws = await tester.connectWebSocket();
    
    // サーバー状態確認
    console.log('\n📊 サーバー状態確認テスト');
    const statusResult = await tester.sendDebugRequest(ws, 'get_status');
    console.log('Status result:', JSON.stringify(statusResult, null, 2));
    
    if (!statusResult.success) {
      console.log('❌ サーバー状態確認失敗 - テスト中止');
      return { success: false, error: 'サーバー状態確認失敗' };
    }

    // 問題の10件検索テスト
    console.log('\n🎯 10件検索テスト（問題調査対象）');
    const smallResult = await tester.sendDebugRequest(ws, 'search_similar', { 
      query: 'テスト', 
      top_k: 10 
    });
    
    console.log('\n=== 10件検索結果分析 ===');
    console.log('Success:', smallResult.success);
    console.log('Error:', smallResult.error);
    console.log('Elapsed:', smallResult.elapsed, 'ms');
    console.log('Data type:', typeof smallResult.data);
    console.log('Data is array:', Array.isArray(smallResult.data));
    
    if (Array.isArray(smallResult.data)) {
      console.log('実際の件数:', smallResult.data.length);
      console.log('期待件数: 10');
      console.log('件数一致:', smallResult.data.length === 10);
      
      if (smallResult.data.length > 0) {
        console.log('最初の項目:', JSON.stringify(smallResult.data[0], null, 2));
      }
      if (smallResult.data.length > 1) {
        console.log('最後の項目:', JSON.stringify(smallResult.data[smallResult.data.length - 1], null, 2));
      }
    } else {
      console.log('❌ データが配列ではありません');
      console.log('Data:', smallResult.data);
    }
    
    console.log('Debug info:', JSON.stringify(smallResult.debugInfo, null, 2));
    console.log('Raw messages count:', smallResult.rawMessages ? smallResult.rawMessages.length : 0);
    
    if (smallResult.rawMessages && smallResult.rawMessages.length > 0) {
      console.log('\n=== 生メッセージ分析 ===');
      smallResult.rawMessages.forEach((msg, index) => {
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

    // 比較のため5件検索も実行
    console.log('\n🔍 5件検索テスト（比較用）');
    const verySmallResult = await tester.sendDebugRequest(ws, 'search_similar', { 
      query: 'テスト', 
      top_k: 5 
    });
    
    console.log('\n=== 5件検索結果分析 ===');
    console.log('Success:', verySmallResult.success);
    console.log('Data length:', Array.isArray(verySmallResult.data) ? verySmallResult.data.length : 'not array');
    console.log('Expected: 5');
    console.log('Match:', Array.isArray(verySmallResult.data) && verySmallResult.data.length === 5);

    // 20件検索も実行
    console.log('\n🔍 20件検索テスト（比較用）');
    const smallerResult = await tester.sendDebugRequest(ws, 'search_similar', { 
      query: 'テスト', 
      top_k: 20 
    });
    
    console.log('\n=== 20件検索結果分析 ===');
    console.log('Success:', smallerResult.success);
    console.log('Data length:', Array.isArray(smallerResult.data) ? smallerResult.data.length : 'not array');
    console.log('Expected: 20');
    console.log('Match:', Array.isArray(smallerResult.data) && smallerResult.data.length === 20);

    return {
      success: true,
      tests: ['status', 'small_10', 'very_small_5', 'smaller_20'],
      results: {
        status: statusResult,
        small_10: smallResult,
        very_small_5: verySmallResult,
        smaller_20: smallerResult
      },
      analysis: {
        problem_identified: smallResult.success && Array.isArray(smallResult.data) && smallResult.data.length !== 10,
        actual_count: Array.isArray(smallResult.data) ? smallResult.data.length : 'not array',
        expected_count: 10,
        streaming_mode: smallResult.debugInfo?.isStreamingMode,
        chunk_count: smallResult.debugInfo?.chunkCount,
        total_messages: smallResult.debugInfo?.totalMessages
      }
    };
  } catch (error) {
    console.log('❌ デバッグテスト実行エラー:', error.message);
    console.log('Error stack:', error.stack);
    return { success: false, error: error.message };
  } finally {
    if (ws) {
      ws.close();
      console.log('✓ WebSocket接続クローズ');
    }
  }
}

// 単体実行用
if (import.meta.url === `file://${process.argv[1]}`) {
  test('WebSocket直接通信デバッグテスト', async () => {
    const result = await runDebugWebSocketTests();
    console.log('\n🎯 最終結果:', JSON.stringify(result, null, 2));
    
    if (!result.success) {
      throw new Error(`デバッグテスト失敗: ${result.error}`);
    }
    
    // 問題の特定
    if (result.analysis.problem_identified) {
      console.log('\n❌ 問題を特定:');
      console.log(`  期待件数: ${result.analysis.expected_count}`);
      console.log(`  実際件数: ${result.analysis.actual_count}`);
      console.log(`  ストリーミングモード: ${result.analysis.streaming_mode}`);
      console.log(`  チャンク数: ${result.analysis.chunk_count}`);
      console.log(`  総メッセージ数: ${result.analysis.total_messages}`);
    } else {
      console.log('\n✓ 10件検索は正常に動作しています');
    }
  });
}