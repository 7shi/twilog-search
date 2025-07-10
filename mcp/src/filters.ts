import { PostInfo } from './database.js';

export interface UserFilter {
  includes?: string[];
  excludes?: string[];
  threshold_min?: number;
  threshold_max?: number;
}

export interface DateFilter {
  from?: string;
  to?: string;
}

export interface FilterOptions {
  userFilter?: UserFilter;
  dateFilter?: DateFilter;
  removeDuplicates?: boolean;
}

export class TwilogFilters {
  static applyUserFilter(posts: PostInfo[], userFilter: UserFilter, userPostCounts: Record<string, number>): PostInfo[] {
    if (!userFilter || Object.keys(userFilter).length === 0) {
      return posts;
    }

    return posts.filter((post) => {
      const user = post.user;
      
      if (!user) {
        return true;
      }

      if (userFilter.includes) {
        if (!userFilter.includes.includes(user)) {
          return false;
        }
      } else if (userFilter.excludes) {
        if (userFilter.excludes.includes(user)) {
          return false;
        }
      }

      const postCount = userPostCounts[user] || 0;

      if (userFilter.threshold_min && postCount < userFilter.threshold_min) {
        return false;
      }

      if (userFilter.threshold_max && postCount > userFilter.threshold_max) {
        return false;
      }

      return true;
    });
  }

  static applyDateFilter(posts: PostInfo[], dateFilter: DateFilter): PostInfo[] {
    if (!dateFilter || Object.keys(dateFilter).length === 0) {
      return posts;
    }

    return posts.filter((post) => {
      const timestamp = post.timestamp;
      
      if (!timestamp) {
        return true;
      }

      try {
        const postDate = new Date(timestamp);

        if (dateFilter.from) {
          const fromDate = new Date(dateFilter.from);
          if (postDate < fromDate) {
            return false;
          }
        }

        if (dateFilter.to) {
          const toDate = new Date(dateFilter.to);
          if (postDate > toDate) {
            return false;
          }
        }

        return true;
      } catch (error) {
        return true;
      }
    });
  }

  static removeDuplicates(posts: PostInfo[]): PostInfo[] {
    const seen = new Map<string, PostInfo>();

    for (const post of posts) {
      const key = `${post.user}:${post.content.trim()}`;
      const existing = seen.get(key);

      if (!existing) {
        seen.set(key, post);
      } else {
        if (post.timestamp < existing.timestamp) {
          seen.set(key, post);
        }
      }
    }

    return Array.from(seen.values());
  }

  static applyAllFilters(
    posts: PostInfo[], 
    options: FilterOptions,
    userPostCounts: Record<string, number> = {}
  ): PostInfo[] {
    let filtered = posts;

    if (options.userFilter) {
      filtered = this.applyUserFilter(filtered, options.userFilter, userPostCounts);
    }

    if (options.dateFilter) {
      filtered = this.applyDateFilter(filtered, options.dateFilter);
    }

    if (options.removeDuplicates) {
      filtered = this.removeDuplicates(filtered);
    }

    return filtered;
  }

  static parseDate(dateStr: string): string | null {
    if (!dateStr.trim()) {
      return null;
    }

    const trimmed = dateStr.trim();

    try {
      if (trimmed.length === 8 && /^\d{8}$/.test(trimmed)) {
        const year = parseInt(trimmed.substring(0, 4));
        const month = parseInt(trimmed.substring(4, 6));
        const day = parseInt(trimmed.substring(6, 8));
        return new Date(year, month - 1, day).toISOString().slice(0, 19).replace('T', ' ');
      }

      if (trimmed.includes('-')) {
        const parts = trimmed.split('-');
        if (parts.length === 3) {
          const year = parseInt(parts[0]);
          const month = parseInt(parts[1]);
          const day = parseInt(parts[2]);
          return new Date(year, month - 1, day).toISOString().slice(0, 19).replace('T', ' ');
        }
      }

      const parsed = new Date(trimmed);
      if (!isNaN(parsed.getTime())) {
        return parsed.toISOString().slice(0, 19).replace('T', ' ');
      }

      return null;
    } catch (error) {
      return null;
    }
  }

  static formatFilterStatus(userFilter?: UserFilter, dateFilter?: DateFilter): string {
    const parts: string[] = [];

    if (userFilter && Object.keys(userFilter).length > 0) {
      if (userFilter.includes) {
        parts.push(`includes: ${userFilter.includes.length}人`);
      } else if (userFilter.excludes) {
        parts.push(`excludes: ${userFilter.excludes.length}人`);
      }

      if (userFilter.threshold_min) {
        parts.push(`min投稿数: ${userFilter.threshold_min}`);
      }

      if (userFilter.threshold_max) {
        parts.push(`max投稿数: ${userFilter.threshold_max}`);
      }
    }

    if (dateFilter && Object.keys(dateFilter).length > 0) {
      if (dateFilter.from && dateFilter.to) {
        parts.push(`期間: ${dateFilter.from} - ${dateFilter.to}`);
      } else if (dateFilter.from) {
        parts.push(`開始: ${dateFilter.from}`);
      } else if (dateFilter.to) {
        parts.push(`終了: ${dateFilter.to}`);
      }
    }

    return parts.length > 0 ? parts.join(', ') : 'フィルターなし';
  }
}