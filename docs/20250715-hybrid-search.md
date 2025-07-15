# SearchEngineハイブリッド検索システム実装レポート

## 概要

SearchEngineクラスに投稿内容・タグ付け理由・要約の3つのベクトル空間を統合したハイブリッド検索システムを実装しました。これにより、用途に応じた6種類の検索モードを選択可能になり、より柔軟で高精度な検索が可能になりました。

## 主要な変更内容

### 1. 外部公開メソッドのシグネチャ変更

#### `vector_search()`
**変更前:**
```python
def vector_search(self, query: str, top_k: int = None) -> List[Tuple[int, float]]:
```

**変更後:**
```python
def vector_search(self, query: str, top_k: int = None, mode: str = "content", weights: List[float] = None) -> List[Tuple[int, float]]:
```

**追加パラメータ:**
- `mode`: 検索モード ("content", "reasoning", "summary", "average", "product", "weighted")
- `weights`: 重み付けモード用の重み（合計1.0）

#### `search_posts_by_text()`
**変更前:**
```python
def search_posts_by_text(self, search_term: str, limit: int = 50) -> List[dict]:
```

**変更後:**
```python
def search_posts_by_text(self, search_term: str, limit: int = 50, source: str = "content") -> List[dict]:
```

**追加パラメータ:**
- `source`: 検索対象ソース ("content", "reasoning", "summary")

#### `search_similar()`
**変更前:**
```python
def search_similar(self, query: str, search_settings: SearchSettings) -> List[Tuple[int, float, dict]]:
```

**変更後:**
```python
def search_similar(self, query: str, search_settings: SearchSettings, mode: str = "content", weights: List[float] = None) -> List[Tuple[int, float, dict]]:
```

**追加パラメータ:**
- `mode`: 検索モード ("content", "reasoning", "summary", "average", "product", "weighted")
- `weights`: 重み付けモード用の重み（合計1.0）

### 2. 新しいデータ構造

```python
# ハイブリッド検索用データ
self.content_vectors: Optional[Any] = None      # 投稿内容のベクトル
self.reasoning_vectors: Optional[Any] = None    # タグ付け理由のベクトル
self.summary_vectors: Optional[Any] = None      # 要約のベクトル
self.tags_data: Dict[int, dict] = {}           # タグ情報（post_id -> {reasoning, summary, tags}）
self.tag_index: Dict[str, List[int]] = {}      # タグ→投稿IDインデックス
```

### 3. 6種類の検索モード

#### 単一ソース検索
- `"content"`: 投稿内容のベクトルを使用
- `"reasoning"`: タグ付け理由のベクトルを使用
- `"summary"`: 要約のベクトルを使用

#### 統合検索
- `"average"`: 3つの類似度の平均値
- `"product"`: 3つの類似度の積（相乗効果）
- `"weighted"`: 重み付け平均（デフォルト: [0.7, 0.2, 0.1]）

### 4. 主要な内部機能

#### `_convert_mode_to_source()`
```python
def _convert_mode_to_source(self, mode: str) -> str:
```
ベクトル検索モードをテキスト検索ソースに変換。ハイブリッドモード（average、product、weighted）はテキスト検索では使用不可能で例外を発生。

#### `_load_vectors()`
```python
def _load_vectors(self, source_dir: str) -> Tuple[List[int], Any]:
```
指定されたディレクトリからベクトルデータを読み込み。存在しないディレクトリはスキップ。

#### `_calculate_similarities()`
```python
def _calculate_similarities(self, query_vector: Any, mode: str, weights: List[float] = None) -> Any:
```
指定されたモードでクエリベクトルとの類似度を計算。

### 5. 条件付き読み込み機能

ベクトル化は重い作業のため、存在するデータのみを読み込み：
- `embeddings/meta.json` → content検索用ベクトル
- `batch/reasoning/meta.json` → reasoning検索用ベクトル
- `batch/summary/meta.json` → summary検索用ベクトル
- `batch/results.jsonl` → タグ情報

利用可能なモードは`_get_available_modes()`で動的に取得。

## 戻り値の拡張

### 検索結果に含まれるタグ情報

`batch/results.jsonl`が存在する場合、全ての検索結果に以下のフィールドが自動的に付加されます：

```python
{
    "post_id": 123,
    "content": "投稿内容",
    "timestamp": "20250101120000",
    "url": "https://...",
    "user": "username",
    # 以下が新たに追加される
    "reasoning": "このツイートは...",  # タグ付けの理由
    "summary": "投稿の要約",          # 投稿の要約
    "tags": ["tag1", "tag2"]        # タグの配列
}
```

### 対象メソッド

以下のメソッドの戻り値が拡張されます：
- `search_posts_by_text()`: 検索結果リストの各要素
- `search_similar()`: タプルの3番目の要素（post_info）
- `vector_search()`: 直接的な戻り値は変更なし（タグ情報はsearch_similarで付加）

## 使用例

### 1. 単一ソース検索
```python
# 投稿内容から検索
results = engine.vector_search("プログラミング", mode="content")

# タグ付け理由から検索
results = engine.vector_search("プログラミング", mode="reasoning")

# 要約から検索
results = engine.vector_search("プログラミング", mode="summary")
```

### 2. 統合検索
```python
# 3つの類似度の平均
results = engine.vector_search("プログラミング", mode="average")

# 3つの類似度の積
results = engine.vector_search("プログラミング", mode="product")

# 重み付け平均（内容重視）
results = engine.vector_search("プログラミング", mode="weighted", weights=[0.7, 0.2, 0.1])
```

### 3. テキスト検索
```python
# 投稿内容からテキスト検索
results = engine.search_posts_by_text("Python", source="content")

# タグ付け理由からテキスト検索
results = engine.search_posts_by_text("Python", source="reasoning")

# 要約からテキスト検索
results = engine.search_posts_by_text("Python", source="summary")
```

### 4. 統合検索（search_similar）
```python
# ベクトル検索（平均モード）
results = engine.search_similar("プログラミング", settings, mode="average")

# テキスト検索（理由から）
results = engine.search_similar("|Python", settings, mode="reasoning")

# ハイブリッドモードをテキスト検索で使用→例外発生
results = engine.search_similar("|Python", settings, mode="weighted")  # ValueError
```

## エラーハンドリング

### 1. 利用不可能なモード
```python
# 利用可能なモードを確認
available_modes = engine._get_available_modes()
# 例: ["content", "reasoning", "average", "product", "weighted"]

# 利用不可能なモードを指定
engine.vector_search("test", mode="summary")  # ValueError: Vector search mode 'summary' is not available
```

### 2. テキスト検索でのハイブリッドモード
```python
# テキスト検索でハイブリッドモードを指定
engine.search_similar("|test", settings, mode="average")
# ValueError: Hybrid mode 'average' is not supported for text search. Use vector search instead.
```

## 後方互換性

すべての新しいパラメータはオプションで、デフォルト値により既存の動作を完全に維持：

```python
# 既存のコードは変更なしで動作
results = engine.vector_search("test")  # mode="content"が適用
results = engine.search_posts_by_text("test")  # source="content"が適用
results = engine.search_similar("test", settings)  # mode="content"が適用
```

## 技術的な特徴

1. **段階的な機能提供**: 存在するベクトルデータに応じて利用可能な機能を動的に提供
2. **統一されたインターフェース**: 単一のメソッドでベクトル/テキスト検索を透過的に切り替え
3. **効率的なメモリ管理**: 条件付き読み込みにより不要なデータの読み込みを回避
4. **堅牢なエラーハンドリング**: 適切なエラーメッセージで問題を明確に通知
5. **保守性の向上**: 統一されたジェネレーターインターフェースによる処理の一貫性

これにより、投稿内容・タグ付け理由・要約の3つの観点から、用途に応じた柔軟で高精度な検索システムが実現されました。