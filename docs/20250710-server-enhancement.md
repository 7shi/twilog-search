# MCPアーキテクチャ統合レポート

## 移行の背景

### 当初の状況（二重実装問題）
**Problem**: MCPサーバー（TypeScript）とSearchEngine（Python）で同じフィルタリング機能が二重実装されており、保守性とコードの一貫性に問題があった
**Solution**: SearchEngineをTwilogServerで活用し、MCPサーバーを単純なラッパーに変更するアーキテクチャ統合を実施

### 技術的課題の発見
**Problem**: SQLiteベースの古い実装（database.ts, filters.ts）とCSVベースの新実装が混在し、一貫性のないデータアクセス層が存在
**Solution**: CSVベースの新アーキテクチャに完全統一し、SQLiteベースの実装を完全削除

## 統合の判断理由

### コード重複の解消
- **Before**: MCPサーバー独自のフィルタリング（TypeScript） + SearchEngine（Python）
- **After**: SearchEngineに一元化、MCPは単純なWebSocketラッパー
- **効果**: 機能追加時の修正箇所を1箇所に集約

### アーキテクチャの一貫性
- **Before**: SQLite（MCP） + CSV（SearchEngine）の二重データアクセス
- **After**: CSVベース統一によるデータアクセス層の一本化
- **効果**: データソースの一元管理と保守性向上

### API設計の統合
- **Before**: MCPとCLIで異なるメソッド名と処理フロー
- **After**: 共通のメソッド名（search_similar, get_user_stats等）で統一
- **効果**: 開発者の学習コストとAPIの複雑性を削減

## 技術的な変更内容

### TwilogServerの拡張
```python
# 追加されたMCP互換メソッド
async def search_similar(self, params: dict = None)  # ベクトル検索+フィルタリング
async def get_user_stats(self, params: dict = None)  # ユーザー統計取得
async def get_database_stats(self, params: dict = None)  # データベース統計
async def search_posts_by_text(self, params: dict = None)  # テキスト検索
```

#### CSVパス自動取得機能
- `meta.json`から相対パスでCSVパスを取得
- embeddings親ディレクトリからの相対パス→絶対パス変換
- SearchEngineの初期化を自動化

### MCPサーバーの簡素化
```typescript
// 削除された複雑な実装
- TwilogDatabase クラス（SQLiteアクセス層）
- TwilogFilters クラス（独自フィルタリング）
- キャッシュ機能（postUserMapCache, postInfoCache等）
- 複雑な集計処理ロジック

// 新しい単純な実装
- WebSocketリクエストの直接転送
- twilog_server.pyの結果をそのまま返却
```

### Search.pyのフロントエンド化
```python
# 削除された機能
from search_engine import SearchEngine  # インポート削除
search = SearchEngine(args.csv_file)    # インスタンス生成削除

# 新しい実装
search_results = client.send_request("search_similar", {"query": query})  # 直接サーバー呼び出し
```

## アーキテクチャ比較

### 変更前のデータフロー
```
[CLI] → SearchEngine → CSV
[MCP] → TwilogDatabase → SQLite
      → TwilogFilters → 独自処理
      → WebSocket → TwilogServer
```

### 変更後のデータフロー
```
[CLI] → WebSocket → TwilogServer → SearchEngine → CSV
[MCP] → WebSocket → TwilogServer → SearchEngine → CSV
```

## 実装の効果

### 保守性の向上
- **フィルタリングロジック**: 1箇所（SearchEngine）での一元管理
- **データアクセス**: CSVベース統一による単純化
- **API設計**: 共通メソッド名による一貫性確保

### 開発効率の改善
- **機能追加**: SearchEngineでの実装のみで全システムに反映
- **デバッグ**: 単一のデータフローによる問題特定の簡素化
- **テスト**: 重複する処理の削除によるテスト工数削減

### 運用の簡素化
- **設定管理**: meta.jsonによるCSVパス自動取得
- **プロセス管理**: TwilogServerのみの管理で完結
- **障害対応**: 単一障害点による原因特定の迅速化

## ファイル変更一覧

### 削除されたファイル
- `mcp/src/database.ts` - SQLiteアクセス層
- `mcp/src/filters.ts` - 独自フィルタリング実装

### 大幅修正されたファイル
- `src/twilog_server.py` - SearchEngine統合とMCPメソッド追加
- `src/search.py` - フロントエンド化とSearchEngine依存削除
- `mcp/src/index.ts` - ラッパー化と独自実装削除

## 技術的な意義

### 設計哲学の統一
- **Before**: 各コンポーネントでの独立実装
- **After**: 単一責任原則に基づく機能分離
- **効果**: システム全体の理解と保守が容易に

### プロトコル設計の改善
- **JSON-RPC統一**: WebSocketベースの統一プロトコル
- **MCPラッパー**: 既存APIの薄いラッパーとしての位置づけ
- **標準準拠**: 業界標準プロトコルの活用

### データアーキテクチャの一貫性
- **CSVベース統一**: 単一データソースによる整合性確保
- **メタデータ管理**: meta.jsonによる設定の一元化
- **相対パス解決**: 柔軟な配置への対応

## 将来への影響

### 拡張性の向上
新機能追加時はSearchEngineでの実装のみで、CLI・MCP両方に自動的に反映される統一アーキテクチャを確立

### 標準化への道筋
JSON-RPC 2.0をベースとした統一APIにより、他のクライアント実装も容易に追加可能

### 保守性の確保
重複コードの削除により、長期的な保守コストを大幅に削減し、システムの安定性を向上

## SearchSettings統合による設定管理の革新

### ステートレス設計への移行
**Problem**: SearchEngineがインスタンス変数として設定を保持していたため、複数クライアントからの同時アクセス時に設定が競合する問題が発生
**Solution**: SearchEngineから状態保持を完全削除し、search()メソッドの引数でSearchSettingsを受け取るステートレス設計に変更

### 設定クラスの統合管理
```python
# 新しいSearchSettingsクラス
class SearchSettings:
    def __init__(self, user_post_counts: Dict[str, int] = None, initial_top_k: int = 10):
        self.user_filter = UserFilterSettings(user_post_counts or {})
        self.date_filter = DateFilterSettings()
        self.top_k = TopKSettings(initial_top_k)
        self.remove_duplicates = True
    
    def to_dict(self) -> Dict[str, Any]:
        # シリアライズ機能
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SearchSettings':
        # デシリアライズ機能
```

### 設定管理のデータフロー
```
[CLI] → SearchSettings → to_dict() → WebSocket → from_dict() → SearchEngine
[MCP] → SearchSettings → to_dict() → WebSocket → from_dict() → SearchEngine
```

### 実装の効果
- **並行性**: 複数クライアントの同時アクセス時の設定競合を解消
- **原子性**: 設定と検索の原子性を保証
- **拡張性**: 新しい設定項目の追加はSearchSettingsクラスの修正のみで対応
- **フィルタリング復活**: `/user`、`/date`、`/top`コマンドによる対話的設定変更を完全復活

## 結論

今回のMCPアーキテクチャ統合により、twilog-searchプロジェクトは以下の状態を達成：

1. **技術的一貫性**: CSVベース統一とSearchEngine中心のアーキテクチャ
2. **運用の簡素化**: 単一データフローによる管理負荷削減
3. **拡張性の確保**: 統一APIによる新機能追加の効率化
4. **ステートレス設計**: SearchSettings統合による並行アクセス対応と設定管理の統一化

この統合は、20250710-sqlite-to-csv.mdで示されたCSVベース移行の完成形として位置づけられ、SearchSettings統合によってプロジェクト全体のアーキテクチャ簡素化と堅牢性向上を完遂した重要なマイルストーンである。