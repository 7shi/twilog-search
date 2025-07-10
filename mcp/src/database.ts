import Database from 'sqlite3';

const sqlite3 = Database.verbose();

export interface PostInfo {
  post_id: number;
  content: string;
  timestamp: string;
  url: string;
  user: string;
}

export interface UserStats {
  user: string;
  post_count: number;
}

export class TwilogDatabase {
  private db: Database.Database | null = null;

  constructor(private dbPath: string) {}

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.db = new sqlite3.Database(this.dbPath, (err) => {
        if (err) {
          reject(new Error(`データベース接続エラー: ${err.message}`));
        } else {
          resolve();
        }
      });
    });
  }

  async close(): Promise<void> {
    return new Promise((resolve) => {
      if (this.db) {
        this.db.close(() => {
          resolve();
        });
      } else {
        resolve();
      }
    });
  }

  async getPostInfos(postIds: number[]): Promise<Record<number, PostInfo>> {
    if (!this.db) {
      throw new Error('データベースが接続されていません');
    }

    if (postIds.length === 0) {
      return {};
    }

    const result: Record<number, PostInfo> = {};
    const batchSize = 100; // 100件ずつ処理

    // バッチ処理で分割して実行
    for (let i = 0; i < postIds.length; i += batchSize) {
      const batch = postIds.slice(i, i + batchSize);
      const batchResult = await this._getPostInfosBatch(batch);
      
      // 結果をマージ
      Object.assign(result, batchResult);
    }

    return result;
  }

  private async _getPostInfosBatch(postIds: number[]): Promise<Record<number, PostInfo>> {
    if (!this.db) {
      throw new Error('データベースが接続されていません');
    }

    return new Promise((resolve, reject) => {
      if (postIds.length === 0) {
        resolve({});
        return;
      }

      const placeholders = postIds.map(() => '?').join(',');
      const query = `
        SELECT p.post_id, p.content, p.timestamp, p.url, up.user 
        FROM posts p
        LEFT JOIN user_posts up ON p.post_id = up.post_id
        WHERE p.post_id IN (${placeholders})
      `;

      this.db!.all(query, postIds, (err, rows: any[]) => {
        if (err) {
          reject(new Error(`クエリ実行エラー: ${err.message}`));
          return;
        }

        const result: Record<number, PostInfo> = {};
        rows.forEach((row) => {
          result[row.post_id] = {
            post_id: row.post_id,
            content: row.content || '',
            timestamp: row.timestamp || '',
            url: row.url || '',
            user: row.user || '',
          };
        });

        resolve(result);
      });
    });
  }

  async getUserStats(): Promise<UserStats[]> {
    if (!this.db) {
      throw new Error('データベースが接続されていません');
    }

    return new Promise((resolve, reject) => {
      const query = `
        SELECT user, COUNT(*) as post_count
        FROM user_posts
        WHERE user IS NOT NULL
        GROUP BY user
        ORDER BY post_count DESC
      `;

      this.db!.all(query, [], (err, rows: any[]) => {
        if (err) {
          reject(new Error(`ユーザー統計取得エラー: ${err.message}`));
          return;
        }

        const result: UserStats[] = rows.map((row) => ({
          user: row.user,
          post_count: row.post_count,
        }));

        resolve(result);
      });
    });
  }

  async getAllPostUserMap(): Promise<Record<number, string>> {
    if (!this.db) {
      throw new Error('データベースが接続されていません');
    }

    return new Promise((resolve, reject) => {
      const query = `
        SELECT post_id, user
        FROM user_posts
        WHERE user IS NOT NULL
      `;

      this.db!.all(query, [], (err, rows: any[]) => {
        if (err) {
          reject(new Error(`全post-userマップ取得エラー: ${err.message}`));
          return;
        }

        const result: Record<number, string> = {};
        rows.forEach((row) => {
          result[row.post_id] = row.user;
        });

        resolve(result);
      });
    });
  }

  async getAllPostInfos(): Promise<Record<number, PostInfo>> {
    if (!this.db) {
      throw new Error('データベースが接続されていません');
    }

    return new Promise((resolve, reject) => {
      const query = `
        SELECT p.post_id, p.content, p.timestamp, p.url, up.user 
        FROM posts p
        LEFT JOIN user_posts up ON p.post_id = up.post_id
      `;

      this.db!.all(query, [], (err, rows: any[]) => {
        if (err) {
          reject(new Error(`全投稿情報取得エラー: ${err.message}`));
          return;
        }

        const result: Record<number, PostInfo> = {};
        rows.forEach((row) => {
          result[row.post_id] = {
            post_id: row.post_id,
            content: row.content || '',
            timestamp: row.timestamp || '',
            url: row.url || '',
            user: row.user || '',
          };
        });

        resolve(result);
      });
    });
  }

  async getPostUserMap(postIds: number[]): Promise<Record<number, string>> {
    if (!this.db) {
      throw new Error('データベースが接続されていません');
    }

    if (postIds.length === 0) {
      return {};
    }

    const result: Record<number, string> = {};
    const batchSize = 100; // 100件ずつ処理

    // バッチ処理で分割して実行
    for (let i = 0; i < postIds.length; i += batchSize) {
      const batch = postIds.slice(i, i + batchSize);
      const batchResult = await this._getPostUserMapBatch(batch);
      
      // 結果をマージ
      Object.assign(result, batchResult);
    }

    return result;
  }

  private async _getPostUserMapBatch(postIds: number[]): Promise<Record<number, string>> {
    if (!this.db) {
      throw new Error('データベースが接続されていません');
    }

    return new Promise((resolve, reject) => {
      if (postIds.length === 0) {
        resolve({});
        return;
      }

      const placeholders = postIds.map(() => '?').join(',');
      const query = `
        SELECT post_id, user
        FROM user_posts
        WHERE post_id IN (${placeholders}) AND user IS NOT NULL
      `;

      this.db!.all(query, postIds, (err, rows: any[]) => {
        if (err) {
          reject(new Error(`post-userマップ取得エラー: ${err.message}`));
          return;
        }

        const result: Record<number, string> = {};
        rows.forEach((row) => {
          result[row.post_id] = row.user;
        });

        resolve(result);
      });
    });
  }

  async getPostsByUser(username: string, limit?: number): Promise<PostInfo[]> {
    if (!this.db) {
      throw new Error('データベースが接続されていません');
    }

    return new Promise((resolve, reject) => {
      const query = `
        SELECT p.post_id, p.content, p.timestamp, p.url, up.user 
        FROM posts p
        JOIN user_posts up ON p.post_id = up.post_id
        WHERE up.user = ?
        ORDER BY p.timestamp DESC
        ${limit ? `LIMIT ${limit}` : ''}
      `;

      this.db!.all(query, [username], (err, rows: any[]) => {
        if (err) {
          reject(new Error(`ユーザー投稿取得エラー: ${err.message}`));
          return;
        }

        const result: PostInfo[] = rows.map((row) => ({
          post_id: row.post_id,
          content: row.content || '',
          timestamp: row.timestamp || '',
          url: row.url || '',
          user: row.user || '',
        }));

        resolve(result);
      });
    });
  }

  async getPostsByDateRange(fromDate?: string, toDate?: string, limit?: number): Promise<PostInfo[]> {
    if (!this.db) {
      throw new Error('データベースが接続されていません');
    }

    return new Promise((resolve, reject) => {
      let query = `
        SELECT p.post_id, p.content, p.timestamp, p.url, up.user 
        FROM posts p
        LEFT JOIN user_posts up ON p.post_id = up.post_id
        WHERE 1=1
      `;
      const params: string[] = [];

      if (fromDate) {
        query += ' AND p.timestamp >= ?';
        params.push(fromDate);
      }

      if (toDate) {
        query += ' AND p.timestamp <= ?';
        params.push(toDate);
      }

      query += ' ORDER BY p.timestamp DESC';

      if (limit) {
        query += ` LIMIT ${limit}`;
      }

      this.db!.all(query, params, (err, rows: any[]) => {
        if (err) {
          reject(new Error(`日付範囲投稿取得エラー: ${err.message}`));
          return;
        }

        const result: PostInfo[] = rows.map((row) => ({
          post_id: row.post_id,
          content: row.content || '',
          timestamp: row.timestamp || '',
          url: row.url || '',
          user: row.user || '',
        }));

        resolve(result);
      });
    });
  }

  async searchPosts(searchTerm: string, limit?: number): Promise<PostInfo[]> {
    if (!this.db) {
      throw new Error('データベースが接続されていません');
    }

    return new Promise((resolve, reject) => {
      const query = `
        SELECT p.post_id, p.content, p.timestamp, p.url, up.user 
        FROM posts p
        LEFT JOIN user_posts up ON p.post_id = up.post_id
        WHERE p.content LIKE ?
        ORDER BY p.timestamp DESC
        ${limit ? `LIMIT ${limit}` : ''}
      `;

      this.db!.all(query, [`%${searchTerm}%`], (err, rows: any[]) => {
        if (err) {
          reject(new Error(`テキスト検索エラー: ${err.message}`));
          return;
        }

        const result: PostInfo[] = rows.map((row) => ({
          post_id: row.post_id,
          content: row.content || '',
          timestamp: row.timestamp || '',
          url: row.url || '',
          user: row.user || '',
        }));

        resolve(result);
      });
    });
  }

  async getDatabaseStats(): Promise<{
    total_posts: number;
    total_users: number;
    date_range: { earliest: string; latest: string };
  }> {
    if (!this.db) {
      throw new Error('データベースが接続されていません');
    }

    return new Promise((resolve, reject) => {
      const queries = {
        totalPosts: 'SELECT COUNT(*) as count FROM posts',
        totalUsers: 'SELECT COUNT(DISTINCT user) as count FROM user_posts WHERE user IS NOT NULL',
        dateRange: 'SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest FROM posts WHERE timestamp IS NOT NULL',
      };

      let results: any = {};
      let completed = 0;

      const handleComplete = () => {
        completed++;
        if (completed === 3) {
          resolve({
            total_posts: results.totalPosts || 0,
            total_users: results.totalUsers || 0,
            date_range: {
              earliest: results.dateRange?.earliest || '',
              latest: results.dateRange?.latest || '',
            },
          });
        }
      };

      this.db!.get(queries.totalPosts, [], (err, row: any) => {
        if (err) {
          reject(new Error(`統計取得エラー: ${err.message}`));
          return;
        }
        results.totalPosts = row.count;
        handleComplete();
      });

      this.db!.get(queries.totalUsers, [], (err, row: any) => {
        if (err) {
          reject(new Error(`統計取得エラー: ${err.message}`));
          return;
        }
        results.totalUsers = row.count;
        handleComplete();
      });

      this.db!.get(queries.dateRange, [], (err, row: any) => {
        if (err) {
          reject(new Error(`統計取得エラー: ${err.message}`));
          return;
        }
        results.dateRange = row;
        handleComplete();
      });
    });
  }
}