#!/usr/bin/env node

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  Tool,
} from '@modelcontextprotocol/sdk/types.js';
import WebSocket from 'ws';
// yamlライブラリを削除（整形テキスト形式に変更）
// 古いSQLiteベースの実装は削除し、twilog_server.pyのラッパーとして動作

// twilog_server.pyのsearch_similarメソッドと同じ形式の結果を期待

interface TwilogServerResponse {
  chunk?: number;
  total_chunks?: number;
  start_rank?: number;
  is_final?: boolean;
  results?: [number, number][];
  vector?: string;
  status?: string;
  ready?: boolean;
  error?: string;
}

class TwilogMCPServer {
  private server: Server;
  private websocketUrl: string = 'ws://localhost:8765';

  constructor(websocketUrl?: string) {
    if (websocketUrl) {
      this.websocketUrl = websocketUrl;
    }
    this.server = new Server(
      {
        name: 'twilog-mcp-server',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupTools();
    this.setupErrorHandling();
  }

  private setupErrorHandling(): void {
    this.server.onerror = (error) => {
      console.error('[MCP Error]:', error);
    };

    process.on('SIGINT', async () => {
      await this.server.close();
      process.exit(0);
    });
  }

  private setupTools(): void {
    // 以下のツールスキーマは、TwilogCommand（src/twilog_client.py）の出力形式と同期している
    // 整形テキスト形式での統一出力により、CLI・MCP両方で一貫した表示を提供
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      return {
        tools: [
          {
            name: 'search_similar',
            description: 'Twilogデータベースに対してベクトル検索を実行します',
            inputSchema: {
              type: 'object',
              properties: {
                query: {
                  type: 'string',
                  description: '検索クエリ',
                },
                top_k: {
                  type: 'integer',
                  description: '表示件数制限（省略時は10件検索）',
                  minimum: 1,
                  maximum: 100,
                },
                user_filter: {
                  type: 'object',
                  description: 'ユーザーフィルタリング設定',
                  properties: {
                    includes: {
                      type: 'array',
                      items: { type: 'string' },
                      description: '含めるユーザー名のリスト',
                    },
                    excludes: {
                      type: 'array',
                      items: { type: 'string' },
                      description: '除外するユーザー名のリスト',
                    },
                    threshold_min: {
                      type: 'integer',
                      description: '最小投稿数',
                      minimum: 1,
                    },
                    threshold_max: {
                      type: 'integer',
                      description: '最大投稿数',
                      minimum: 1,
                    },
                  },
                },
                date_filter: {
                  type: 'object',
                  description: '日付フィルタリング設定',
                  properties: {
                    from: {
                      type: 'string',
                      description: '開始日時（YYYY-MM-DD HH:MM:SS形式）',
                    },
                    to: {
                      type: 'string',
                      description: '終了日時（YYYY-MM-DD HH:MM:SS形式）',
                    },
                  },
                },
                mode: {
                  type: 'string',
                  description: '検索モード',
                  enum: ['content', 'reasoning', 'summary', 'average', 'maximum', 'minimum'],
                  default: 'content',
                },
                weights: {
                  type: 'array',
                  items: { type: 'number' },
                  description: '重み付けモード用の重み（合計1.0想定）',
                },
              },
              required: ['query'],
            },
          },
          {
            name: 'get_status',
            description: 'Twilog Serverの稼働状況を確認します',
            inputSchema: {
              type: 'object',
              properties: {
                websocket_url: {
                  type: 'string',
                  description: 'WebSocket URL',
                  default: 'ws://localhost:8765',
                },
              },
            },
          },
          {
            name: 'get_user_stats',
            description: 'ユーザー別投稿統計を取得します',
            inputSchema: {
              type: 'object',
              properties: {
                limit: {
                  type: 'integer',
                  description: '取得件数制限',
                  minimum: 1,
                  maximum: 1000,
                  default: 50,
                },
              },
            },
          },
          {
            name: 'get_database_stats',
            description: 'データベース全体の統計情報を取得します',
            inputSchema: {
              type: 'object',
              properties: {
              },
            },
          },
          {
            name: 'search_posts_by_text',
            description: 'テキスト検索（LIKE検索）を実行します',
            inputSchema: {
              type: 'object',
              properties: {
                search_term: {
                  type: 'string',
                  description: '検索文字列',
                },
                limit: {
                  type: 'integer',
                  description: '表示件数制限',
                  minimum: 1,
                  maximum: 1000,
                  default: 50,
                },
                source: {
                  type: 'string',
                  description: '検索対象ソース',
                  enum: ['content', 'reasoning', 'summary'],
                  default: 'content',
                },
              },
              required: ['search_term'],
            },
          },
          {
            name: 'embed_text',
            description: 'テキストをベクトル化します（デバッグ用）',
            inputSchema: {
              type: 'object',
              properties: {
                text: {
                  type: 'string',
                  description: 'ベクトル化するテキスト',
                },
              },
              required: ['text'],
            },
          },
        ] as Tool[],
      };
    });

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      try {
        switch (name) {
          case 'search_similar':
            return await this.handleTwilogSearch(args);
          case 'get_status':
            return await this.handleTwilogServerStatus(args);
          case 'get_user_stats':
            return await this.handleGetUserStats(args);
          case 'get_database_stats':
            return await this.handleGetDatabaseStats(args);
          case 'search_posts_by_text':
            return await this.handleSearchPostsByText(args);
          case 'embed_text':
            return await this.handleEmbedText(args);
          default:
            throw new Error(`Unknown tool: ${name}`);
        }
      } catch (error) {
        return {
          isError: true,
          content: [
            {
              type: 'text',
              text: `エラー: ${error instanceof Error ? error.message : String(error)}`,
            },
          ],
        };
      }
    });
  }

  private async connectWebSocket(url: string): Promise<WebSocket> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      let timeoutId: NodeJS.Timeout;
      
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
        } else if (error.message.includes('ETIMEDOUT')) {
          reject(new Error('サーバーへの接続がタイムアウトしました'));
        } else {
          reject(new Error(`WebSocket接続エラー: ${error.message}`));
        }
      });

      timeoutId = setTimeout(() => {
        ws.terminate();
        reject(new Error('サーバーへの接続がタイムアウトしました'));
      }, 5000);
    });
  }

  private async sendWebSocketRequest(url: string, request: any): Promise<any> {
    const ws = await this.connectWebSocket(url);
    
    return new Promise((resolve, reject) => {
      let allResults: any[] = [];
      let isStreamingMode = false;
      let streamingChunks: any[] = [];
      
      ws.on('message', (data) => {
        try {
          const response = JSON.parse(data.toString());
          
          // JSON-RPCフォーマットのチェック
          if (response.jsonrpc === "2.0") {
            if (response.error) {
              ws.close();
              reject(new Error(`サーバーエラー: ${response.error.message}`));
              return;
            }
            
            const result = response.result;
            
            // Streaming Extensions形式の処理（embed_server.pyの仕様に合わせる）
            if (result && typeof result === 'object') {
              // dataフィールドが存在する場合（twilog_client.pyのStreaming Extensions）
              if ('data' in result && Array.isArray(result.data)) {
                isStreamingMode = true;
                streamingChunks.push(result);
                allResults.push(...result.data);
                
                // moreフィールドはresponseのトップレベルに存在（embed_server.py仕様）
                if (response.more === false || response.more === undefined) {
                  ws.close();
                  // twilog_client.pyのvector_searchメソッドと同様の処理
                  // 分割送信されたデータを結合して返す
                  resolve(allResults);
                  return;
                }
              }
              // resultsフィールドが存在する場合（従来形式との互換性）
              else if ('results' in result && Array.isArray(result.results)) {
                isStreamingMode = true;
                streamingChunks.push(result);
                allResults.push(...result.results);
                
                // is_finalフィールドでストリーミング継続判定
                if (result.is_final === true) {
                  ws.close();
                  resolve(allResults);
                  return;
                }
              }
              // 単一レスポンス（ストリーミング以外）
              else if (!isStreamingMode) {
                ws.close();
                resolve(result);
                return;
              }
            }
            // プリミティブ型の結果
            else if (!isStreamingMode) {
              ws.close();
              resolve(result);
              return;
            }
          } else {
            ws.close();
            reject(new Error('サーバーがJSON-RPC 2.0形式に対応していません'));
          }
        } catch (error) {
          ws.close();
          reject(new Error(`レスポンス解析エラー: ${error}`));
        }
      });

      ws.on('error', (error) => {
        reject(new Error(`WebSocket通信エラー: ${error.message}`));
      });

      ws.on('close', () => {
        // 予期しない切断の場合
        if (isStreamingMode && allResults.length > 0) {
          // 分割送信が途中で切断された場合も、収集済みのデータを返す
          resolve(allResults);
        } else if (!isStreamingMode) {
          reject(new Error('WebSocket接続が予期せず終了しました'));
        }
      });

      ws.send(JSON.stringify(request));
    });
  }

  private async handleTwilogServerStatus(args: any) {
    const url = args.websocket_url || this.websocketUrl;
    
    try {
      const request = {
        jsonrpc: "2.0",
        method: "get_status",
        params: {},
        id: 1
      };
      const response = await this.sendWebSocketRequest(url, request);
      
      const statusIcon = response.ready ? '🟢' : '🔴';
      const statusText = response.ready ? '稼働中' : '停止中';
      
      let result = `${statusIcon} Twilog Server Status\n\n`;
      result += `状態: ${statusText}\n`;
      result += `サーバータイプ: ${response.server_type || 'Unknown'}\n`;
      if (response.model) {
        result += `モデル: ${response.model}\n`;
      }
      
      if (response.data_stats) {
        result += `\n📊 データ統計:\n`;
        result += `・投稿数: ${response.data_stats.total_posts?.toLocaleString() || 0}件\n`;
        result += `・ユーザー数: ${response.data_stats.total_users?.toLocaleString() || 0}人\n`;
        if (response.data_stats.total_summaries) {
          result += `・要約数: ${response.data_stats.total_summaries.toLocaleString()}件\n`;
        }
        if (response.data_stats.total_tags) {
          result += `・タグ数: ${response.data_stats.total_tags.toLocaleString()}件\n`;
        }
      }
      
      return {
        content: [
          {
            type: 'text',
            text: result,
          },
        ],
      };
    } catch (error) {
      return {
        content: [
          {
            type: 'text',
            text: `Twilog Serverに接続できません: ${error instanceof Error ? error.message : String(error)}`,
          },
        ],
      };
    }
  }


  private async handleTwilogSearch(args: any) {
    const { query, top_k, user_filter, date_filter, mode, weights } = args;
    
    if (!query) {
      throw new Error('検索クエリが指定されていません');
    }

    try {
      // twilog_server.pyのsearch_similarメソッドを直接呼び出し
      const params: any = { query };
      
      // modeとweightsを追加
      if (mode !== undefined) {
        params.mode = mode;
      }
      
      if (weights !== undefined) {
        params.weights = weights;
      }
      
      // 個別のオプションをsettingsとしてまとめる
      const settings: any = {};
      
      if (top_k !== undefined) {
        settings.top_k = top_k;
      }
      
      if (user_filter !== undefined) {
        settings.user_filter = user_filter;
      }
      
      if (date_filter !== undefined) {
        settings.date_filter = date_filter;
      }
      
      
      // settingsが空でない場合のみ追加
      if (Object.keys(settings).length > 0) {
        params.settings = settings;
      }
      
      const request = {
        jsonrpc: "2.0",
        method: "search_similar",
        params: params,
        id: Date.now()
      };
      
      const results = await this.sendWebSocketRequest(this.websocketUrl, request);
      
      if (!results || results.length === 0) {
        return {
          content: [
            {
              type: 'text',
              text: '検索結果が見つかりませんでした',
            },
          ],
        };
      }
      
      // 整形テキスト形式に変換
      let resultText = `🔍 検索結果: ${results.length}件 (クエリ: "${query}")\n\n`;
      
      results.forEach((result: any, index: number) => {
        const post = result.post;
        const score = result.score.toFixed(3);
        const rank = index + 1;
        
        resultText += `${rank}. [${score}] @${post.user} (${post.timestamp}) ${post.url}\n`;
        
        // 投稿内容の処理（改行保持、空行詰め）
        const content = post.content.replace(/\n\s*\n/g, '\n').trim();
        resultText += `   ${content}\n\n`;
      });
      
      return {
        content: [
          {
            type: 'text',
            text: resultText,
          },
        ],
      };
    } catch (error) {
      throw new Error(`検索に失敗: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

// performSearchメソッドは不要（twilog_server.pyで処理）

// キャッシュ初期化は不要（twilog_server.pyで処理）

// getPostUserMapメソッドは不要（twilog_server.pyで処理）

// isUserAllowedメソッドは不要（twilog_server.pyで処理）

  private async handleGetUserStats(args: any) {
    const { limit = 50 } = args;

    try {
      // twilog_server.pyのget_user_statsメソッドを呼び出し
      const request = {
        jsonrpc: "2.0",
        method: "get_user_stats",
        params: { limit },
        id: Date.now()
      };
      
      const userStats = await this.sendWebSocketRequest(this.websocketUrl, request);
      
      let resultText = `👥 ユーザー別投稿統計 (上位${userStats.length}人)\n\n`;
      
      userStats.forEach((stat: any, index: number) => {
        const rank = index + 1;
        const postCount = stat.post_count.toLocaleString();
        resultText += `${rank}. ${stat.user}: ${postCount}投稿\n`;
      });
      
      return {
        content: [
          {
            type: 'text',
            text: resultText,
          },
        ],
      };
    } catch (error) {
      throw new Error(`ユーザー統計取得に失敗: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  private async handleGetDatabaseStats(args: any) {
    try {
      // twilog_server.pyのget_database_statsメソッドを呼び出し
      const request = {
        jsonrpc: "2.0",
        method: "get_database_stats",
        params: {},
        id: Date.now()
      };
      
      const stats = await this.sendWebSocketRequest(this.websocketUrl, request);
      
      let resultText = `📊 データベース統計\n\n`;
      resultText += `総投稿数: ${stats.total_posts?.toLocaleString() || 0}件\n`;
      resultText += `総ユーザー数: ${stats.total_users?.toLocaleString() || 0}人\n`;
      
      if (stats.date_range) {
        resultText += `データ期間: ${stats.date_range.earliest} ～ ${stats.date_range.latest}\n`;
      }
      
      return {
        content: [
          {
            type: 'text',
            text: resultText,
          },
        ],
      };
    } catch (error) {
      throw new Error(`データベース統計取得に失敗: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  private async handleSearchPostsByText(args: any) {
    const { search_term, limit = 50, source = 'content' } = args;

    if (!search_term) {
      throw new Error('検索文字列が指定されていません');
    }

    try {
      // twilog_server.pyのsearch_posts_by_textメソッドを呼び出し
      const request = {
        jsonrpc: "2.0",
        method: "search_posts_by_text",
        params: { search_term, limit, source },
        id: Date.now()
      };
      
      const posts = await this.sendWebSocketRequest(this.websocketUrl, request);
      
      if (posts.length === 0) {
        return {
          content: [
            {
              type: 'text',
              text: `検索結果が見つかりませんでした (検索語: "${search_term}")`,
            },
          ],
        };
      }

      let resultText = `📝 テキスト検索結果: ${posts.length}件 (検索語: "${search_term}")\n\n`;
      
      posts.forEach((post: any, index: number) => {
        const rank = index + 1;
        resultText += `${rank}. @${post.user} (${post.timestamp})\n`;
        
        // 投稿内容の処理（改行保持、空行詰め）
        const content = post.content.replace(/\n\s*\n/g, '\n').trim();
        resultText += `   ${content}\n\n`;
      });
      
      return {
        content: [
          {
            type: 'text',
            text: resultText,
          },
        ],
      };
    } catch (error) {
      throw new Error(`テキスト検索に失敗: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  private async handleEmbedText(args: any) {
    const { text } = args;

    if (!text) {
      throw new Error('ベクトル化するテキストが指定されていません');
    }

    try {
      const request = {
        jsonrpc: "2.0",
        method: "embed_text",
        params: { text },
        id: Date.now()
      };
      
      const result = await this.sendWebSocketRequest(this.websocketUrl, request);

      if (result.vector) {
        // Base64データの情報を表示
        const vectorLength = result.vector.length;
        const vectorPreview = result.vector.substring(0, 20);
        
        return {
          content: [
            {
              type: 'text',
              text: `ベクトル化成功:
入力テキスト: "${text}"
Base64データ長: ${vectorLength}文字
Base64データ（先頭20文字）: ${vectorPreview}...`,
            },
          ],
        };
      } else {
        return {
          content: [
            {
              type: 'text',
              text: `ベクトル化は完了しましたが、ベクトルデータが返されませんでした。
入力テキスト: "${text}"
レスポンス: ${JSON.stringify(result)}`,
            },
          ],
        };
      }
    } catch (error) {
      throw new Error(`ベクトル化に失敗: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  async run(): Promise<void> {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('Twilog MCP Server running on stdio');
  }
}

// コマンドライン引数の解析
function parseArgs(): { websocketUrl?: string; help?: boolean } {
  const args = process.argv.slice(2);
  const result: { websocketUrl?: string; help?: boolean } = {};

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    
    if (arg === '--help' || arg === '-h') {
      result.help = true;
    } else if (arg === '--websocket' || arg === '--ws') {
      result.websocketUrl = args[++i];
    } else if (arg.startsWith('--websocket=')) {
      result.websocketUrl = arg.split('=')[1];
    }
  }

  return result;
}

function showHelp() {
  console.error(`Twilog MCP Server

使用方法:
  node dist/index.js [オプション]

オプション:
  --websocket, --ws URL       WebSocket URL (デフォルト: ws://localhost:8765)
  --help, -h                  このヘルプを表示

例:
  node dist/index.js --websocket=ws://localhost:8765
`);
}

const { websocketUrl, help } = parseArgs();

if (help) {
  showHelp();
  process.exit(0);
}

const server = new TwilogMCPServer(websocketUrl);
server.run().catch(console.error);
