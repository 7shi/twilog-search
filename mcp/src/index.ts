#!/usr/bin/env node

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  Tool,
} from '@modelcontextprotocol/sdk/types.js';
import WebSocket from 'ws';
import { TwilogDatabase, PostInfo } from './database.js';
import { TwilogFilters, UserFilter, DateFilter, FilterOptions } from './filters.js';

interface SearchResult {
  post_id: number;
  similarity: number;
}

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
  private database: TwilogDatabase | null = null;
  private websocketUrl: string = 'ws://localhost:8765';
  private defaultDbPath: string = '../twilog.db';
  private postUserMapCache: Record<number, string> = {};
  private postInfoCache: Record<number, PostInfo> = {};
  private userPostCountsCache: Record<string, number> = {};

  constructor(defaultDbPath?: string, websocketUrl?: string) {
    if (defaultDbPath) {
      this.defaultDbPath = defaultDbPath;
    }
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
      if (this.database) {
        await this.database.close();
      }
      await this.server.close();
      process.exit(0);
    });
  }

  private setupTools(): void {
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
                  type: 'number',
                  description: '表示件数制限（省略時は10件検索）',
                  minimum: 1,
                  maximum: 1000,
                },
                user_filter: {
                  type: 'object',
                  description: 'ユーザーフィルタリング設定',
                  properties: {
                    includes: {
                      type: 'array',
                      items: { type: 'string' },
                      description: '対象ユーザーリスト',
                    },
                    excludes: {
                      type: 'array',
                      items: { type: 'string' },
                      description: '除外ユーザーリスト',
                    },
                    threshold_min: {
                      type: 'number',
                      description: '投稿数下限',
                    },
                    threshold_max: {
                      type: 'number',
                      description: '投稿数上限',
                    },
                  },
                },
                date_filter: {
                  type: 'object',
                  description: '日付フィルタリング設定',
                  properties: {
                    from: {
                      type: 'string',
                      description: '開始日時 (YYYY-MM-DD HH:MM:SS)',
                    },
                    to: {
                      type: 'string',
                      description: '終了日時 (YYYY-MM-DD HH:MM:SS)',
                    },
                  },
                },
                remove_duplicates: {
                  type: 'boolean',
                  description: '重複除去を有効にする',
                  default: true,
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
                  type: 'number',
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
                  type: 'number',
                  description: '表示件数制限',
                  minimum: 1,
                  maximum: 1000,
                  default: 50,
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
                  // twilog_client.pyのsearch_similarメソッドと同様の処理
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
      
      return {
        content: [
          {
            type: 'text',
            text: `Twilog Server Status:
- Status: ${response.status || 'unknown'}
- Ready: ${response.ready || false}
- URL: ${url}`,
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
    const { 
      query, 
      top_k, 
      user_filter,
      date_filter,
      remove_duplicates = true
    } = args;
    
    // 検索開始ログ
    
    if (!query) {
      throw new Error('検索クエリが指定されていません');
    }

    try {
      const database = new TwilogDatabase(this.defaultDbPath);
      await database.connect();

      try {
        const targetCount = top_k || 10;
        let results: any[] = [];
        let searchOffset = 0;
        const batchSize = Math.max(targetCount * 2, 100); // フィルタリングを考慮して多めに取得

        // フィルタリングが必要な場合は、十分な結果が得られるまで検索を続ける
        const hasFiltering = user_filter || date_filter || remove_duplicates;
        
        // 最初に全件のpost_idと類似度のみ取得
        const searchResults = await this.performSearch(query, null); // top_k: null で全件取得
        
        if (searchResults.length === 0) {
          results = [];
        } else {
          let filteredResults = searchResults;

          if (hasFiltering) {
            // ユーザー統計をキャッシュから取得
            const userPostCounts = this.userPostCountsCache;

            // user_filterのみ適用（post_idレベルで可能）
            if (user_filter) {
              // キャッシュからユーザー情報を取得
              const postUserMap = this.getPostUserMap(filteredResults.map(r => r.post_id));
              
              filteredResults = filteredResults.filter(result => {
                const user = postUserMap[result.post_id];
                if (!user) return true; // ユーザー情報がない場合は通す
                
                return this.isUserAllowed(user, user_filter, userPostCounts);
              });
            }

            // キャッシュから投稿情報を取得してフィルタリング
            let processedResults: any[] = [];
            
            for (const result of filteredResults) {
              const postInfo = this.postInfoCache[result.post_id];
              if (!postInfo) continue;
              
              const combinedResult = {
                similarity: result.similarity,
                ...postInfo,
              };
              
              // date_filterを適用
              if (date_filter) {
                const filterOptions: FilterOptions = {
                  dateFilter: date_filter,
                  removeDuplicates: false,
                };
                const filtered = TwilogFilters.applyAllFilters([combinedResult], filterOptions, {});
                if (filtered.length === 0) continue;
              }
              
              processedResults.push(combinedResult);
              
              // 必要数に達したら終了
              if (processedResults.length >= targetCount) {
                break;
              }
            }

            // 重複除去を最後に適用
            if (remove_duplicates) {
              processedResults = TwilogFilters.removeDuplicates(processedResults);
            }

            results = processedResults;
          } else {
            // フィルタリングなしの場合はキャッシュから必要な分だけ取得
            const topResults = filteredResults.slice(0, targetCount);
            
            results = topResults
              .map((result) => {
                const postInfo = this.postInfoCache[result.post_id];
                if (!postInfo) return null;
                
                return {
                  similarity: result.similarity,
                  ...postInfo,
                };
              })
              .filter(Boolean) as any[];
          }
        }

        // 最終的に必要な件数に調整
        results = results.slice(0, targetCount);

        // フィルタリング後にランクを正しく振り直す
        results = results.map((result, index) => ({
          ...result,
          rank: index + 1,
        }));

        if (results.length === 0) {
          return {
            content: [
              {
                type: 'text',
                text: '検索結果が見つかりませんでした',
              },
            ],
          };
        }

        const filterStatus = TwilogFilters.formatFilterStatus(user_filter, date_filter);
        
        const resultText = results
          .map((result: any) => 
            `${result.rank}位: ${result.similarity.toFixed(5)} - @${result.user || 'unknown'}
${result.content}
[${result.timestamp}] ${result.url || ''}
---`
          )
          .join('\n');

        return {
          content: [
            {
              type: 'text',
              text: `検索結果 (クエリ: "${query}", 件数: ${results.length}):
フィルター: ${filterStatus}

${resultText}`,
            },
          ],
        };
      } finally {
        await database.close();
      }
    } catch (error) {
      throw new Error(`検索に失敗: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  private async performSearch(query: string, top_k?: number | null): Promise<SearchResult[]> {
    const params = (top_k !== null && top_k !== undefined) ? { query, top_k } : { query };
    const request = {
      jsonrpc: "2.0",
      method: "search_similar",
      params,
      id: Date.now()
    };
    const results = await this.sendWebSocketRequest(this.websocketUrl, request);
    
    return results.map(([post_id, similarity]: [number, number]) => ({
      post_id,
      similarity,
    }));
  }

  private async initializeCache(): Promise<void> {
    try {
      console.error('データキャッシュ初期化中...');
      const database = new TwilogDatabase(this.defaultDbPath);
      await database.connect();
      
      try {
        // post-userマップを読み込み
        this.postUserMapCache = await database.getAllPostUserMap();
        console.error(`post-userマップキャッシュ完了 - ${Object.keys(this.postUserMapCache).length}件`);
        
        // 全投稿情報を読み込み
        this.postInfoCache = await database.getAllPostInfos();
        console.error(`投稿情報キャッシュ完了 - ${Object.keys(this.postInfoCache).length}件`);
        
        // ユーザー投稿数統計を読み込み
        const userStats = await database.getUserStats();
        userStats.forEach(stat => {
          this.userPostCountsCache[stat.user] = stat.post_count;
        });
        console.error(`ユーザー統計キャッシュ完了 - ${userStats.length}人`);
        
        console.error('データキャッシュ初期化完了');
      } finally {
        await database.close();
      }
    } catch (error) {
      console.error('データキャッシュ初期化失敗:', error);
      // キャッシュ初期化に失敗しても動作を継続
    }
  }

  private getPostUserMap(postIds: number[]): Record<number, string> {
    if (postIds.length === 0) {
      return {};
    }

    const result: Record<number, string> = {};
    for (const postId of postIds) {
      if (this.postUserMapCache[postId]) {
        result[postId] = this.postUserMapCache[postId];
      }
    }
    return result;
  }

  private isUserAllowed(user: string, userFilter: UserFilter, userPostCounts: Record<string, number>): boolean {
    if (!userFilter || Object.keys(userFilter).length === 0) {
      return true;
    }

    // includes/excludesのチェック（排他的）
    if (userFilter.includes) {
      if (!userFilter.includes.includes(user)) {
        return false;
      }
    } else if (userFilter.excludes) {
      if (userFilter.excludes.includes(user)) {
        return false;
      }
    }

    // threshold系のチェック（組み合わせ可能）
    const postCount = userPostCounts[user] || 0;

    if (userFilter.threshold_min && postCount < userFilter.threshold_min) {
      return false;
    }

    if (userFilter.threshold_max && postCount > userFilter.threshold_max) {
      return false;
    }

    return true;
  }

  private async handleGetUserStats(args: any) {
    const { limit = 50 } = args;

    try {
      // キャッシュからユーザー統計を取得してソート
      const userStats = Object.entries(this.userPostCountsCache)
        .map(([user, post_count]) => ({ user, post_count }))
        .sort((a, b) => b.post_count - a.post_count);
      
      const limitedStats = userStats.slice(0, limit);

      const statsText = limitedStats
        .map((stat, index) => `${index + 1}位: ${stat.user} (${stat.post_count}投稿)`)
        .join('\n');

      return {
        content: [
          {
            type: 'text',
            text: `ユーザー別投稿統計 (上位${limitedStats.length}人):

${statsText}

総ユーザー数: ${userStats.length}人`,
          },
        ],
      };
    } catch (error) {
      throw new Error(`ユーザー統計取得に失敗: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  private async handleGetDatabaseStats(args: any) {
    try {
      // キャッシュから統計を計算
      const totalPosts = Object.keys(this.postInfoCache).length;
      const totalUsers = Object.keys(this.userPostCountsCache).length;
      
      // 日付範囲をキャッシュから計算
      const timestamps = Object.values(this.postInfoCache)
        .map(post => post.timestamp)
        .filter(ts => ts)
        .sort();
      
      const earliest = timestamps[0] || '';
      const latest = timestamps[timestamps.length - 1] || '';

      return {
        content: [
          {
            type: 'text',
            text: `データベース統計:

総投稿数: ${totalPosts.toLocaleString()}件
総ユーザー数: ${totalUsers.toLocaleString()}人
データ期間: ${earliest} ～ ${latest}`,
          },
        ],
      };
    } catch (error) {
      throw new Error(`データベース統計取得に失敗: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  private async handleSearchPostsByText(args: any) {
    const { search_term, limit = 50 } = args;

    if (!search_term) {
      throw new Error('検索文字列が指定されていません');
    }

    try {
      // キャッシュからテキスト検索
      const posts = Object.values(this.postInfoCache)
        .filter(post => post.content.toLowerCase().includes(search_term.toLowerCase()))
        .sort((a, b) => b.timestamp.localeCompare(a.timestamp)) // 新しい順
        .slice(0, limit);

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

      const resultText = posts
        .map((post, index) => 
          `${index + 1}位: @${post.user || 'unknown'}
${post.content}
[${post.timestamp}] ${post.url || ''}
---`
        )
        .join('\n');

      return {
        content: [
          {
            type: 'text',
            text: `テキスト検索結果 (検索語: "${search_term}", 件数: ${posts.length}):

${resultText}`,
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
    // キャッシュ初期化
    await this.initializeCache();
    
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('Twilog MCP Server running on stdio');
  }
}

// コマンドライン引数の解析
function parseArgs(): { dbPath?: string; websocketUrl?: string; help?: boolean } {
  const args = process.argv.slice(2);
  const result: { dbPath?: string; websocketUrl?: string; help?: boolean } = {};

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    
    if (arg === '--help' || arg === '-h') {
      result.help = true;
    } else if (arg === '--db' || arg === '--database') {
      result.dbPath = args[++i];
    } else if (arg === '--websocket' || arg === '--ws') {
      result.websocketUrl = args[++i];
    } else if (arg.startsWith('--db=')) {
      result.dbPath = arg.split('=')[1];
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
  --db, --database PATH       デフォルトのデータベースファイルパス (デフォルト: twilog.db)
  --websocket, --ws URL       WebSocket URL (デフォルト: ws://localhost:8765)
  --help, -h                  このヘルプを表示

例:
  node dist/index.js --db /path/to/custom.db
  node dist/index.js --db=mydata.db --websocket=ws://localhost:8765
`);
}

const { dbPath, websocketUrl, help } = parseArgs();

if (help) {
  showHelp();
  process.exit(0);
}

const server = new TwilogMCPServer(dbPath, websocketUrl);
server.run().catch(console.error);
