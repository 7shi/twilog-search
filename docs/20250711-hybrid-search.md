# V|T複合検索の導入レポート

**日付**: 2025年7月11日  
**カテゴリ**: 検索機能拡張  
**影響範囲**: SearchEngine, TwilogServer, text_proc  

## 概要

ベクトル検索とテキスト検索を組み合わせた複合検索機能（V|T構文）を、既存のクライアント側APIを変更せずに実装した技術レポート。パイプライン構文による統一的なクエリ処理と、効率的なフィルタリングアルゴリズムを実現。

## 背景と課題

### 検索機能の限界
従来システムでは、ベクトル検索（意味的類似性）とテキスト検索（文字列マッチング）が完全に分離されており、以下の課題があった：

- **機能選択の硬直性**: ユーザーはベクトル検索かテキスト検索かを事前に決める必要があった
- **複合条件の困難**: 「機械学習に関連し、かつspamを含まない投稿」のような複合条件を一度に指定できなかった
- **API分離による非効率**: 複合検索を実現するには複数のAPI呼び出しとクライアント側でのデータ結合が必要だった

### テキスト検索の機能不足
既存のテキスト検索では単純な部分一致のみで、以下の高度な検索ニーズに対応できなかった：

- **複数キーワードのAND条件**: 「python AND 機械学習」のような複合条件
- **除外条件**: 「機械学習 -spam」のような否定条件
- **フレーズ検索**: 「"hello world"」のようなスペースを含むフレーズ
- **特殊文字の扱い**: エスケープ処理による柔軟な検索語指定

## 技術的アプローチ

### 1. シェル風パース機能の実装（text_proc.py）

#### parse_search_terms関数
高度なテキスト検索のためのクエリパース機能を実装：

```python
# 例: "hello world" -spam \-minus
include_terms, exclude_terms = parse_search_terms(query)
# include_terms: ["hello world", "-minus"]
# exclude_terms: ["spam"]
```

**特徴**:
- ダブルクォート囲みによるフレーズ検索
- マイナス記号による除外条件
- バックスラッシュによるエスケープ処理
- 空白の柔軟な処理

#### parse_pipeline_query関数
V|T構文の解析機能を実装：

```python
# 例: "機械学習 | \"hello world\" -spam"
vector_query, text_query = parse_pipeline_query(query)
# vector_query: "機械学習"
# text_query: "\"hello world\" -spam"
```

**特徴**:
- パイプ記号による明確な分離
- エスケープ処理（\\|）による文字としてのパイプ使用
- V=""（テキストのみ）、T=""（ベクトルのみ）への対応

### 2. SearchEngine拡張

#### 効率的フィルタリングアルゴリズム
従来の全件処理→フィルタリング方式から、類似度順早期終了方式に変更：

```python
def vector_search(self, query_vector, top_k=None, text_filter=""):
    # 類似度順にソート
    sorted_indices = torch.argsort(similarities, descending=True)
    
    # 1件ずつフィルタリングしてtop_kで早期終了
    results = []
    for idx in sorted_indices:
        if text_filter and not self.is_post_text_match(post_id, include_terms, exclude_terms):
            continue
        results.append((post_id, similarity))
        if top_k and len(results) >= top_k:
            break
```

**利点**:
- **処理効率**: 不要な投稿の詳細取得を回避
- **メモリ効率**: 中間結果の大量保持を回避
- **レスポンス性**: top_kに達した時点で即座に処理終了

#### 単一投稿フィルタリング関数
コードの重複を排除し、一貫した判定ロジックを実現：

```python
def is_post_text_match(self, post_id, include_terms, exclude_terms):
    content = self.data_access.posts_data.get(post_id, {}).get("content", "").lower()
    
    # AND条件（全てのinclude_termsが含まれる）
    if include_terms and not all(term.lower() in content for term in include_terms):
        return False
    
    # NOT条件（いずれのexclude_termsも含まれない）
    if exclude_terms and any(term.lower() in content for term in exclude_terms):
        return False
    
    return True
```

### 3. TwilogServerでの透過的な統合

#### クエリ再解釈による後方互換性
既存のAPIを変更せずに、サーバー側でクエリを再解釈：

```python
async def search_similar(self, params=None):
    query = params.get("query")
    
    # V|T検索の解析
    vector_query, text_filter = parse_pipeline_query(query)
    
    if not vector_query:
        # テキスト検索のみ（|text形式）
        return self.search_engine.search_posts_by_text(text_filter, limit=top_k)
    else:
        # ベクトル検索またはベクトル+テキスト複合検索
        return self.search_engine.search_similar(query_vector, search_settings, text_filter)
```

**アーキテクチャ上の利点**:
- **クライアント透過性**: CLI、MCPクライアント共に変更不要
- **段階的移行**: 既存クエリは従来通り動作
- **統一インターフェース**: 一つのAPIで3種類の検索を提供

## 実装結果

### 機能拡張
V|T複合検索により以下の検索パターンが可能になった：

1. **ベクトル検索のみ**: `機械学習`
2. **テキスト検索のみ**: `| "hello world" -spam`
3. **複合検索**: `機械学習 | -spam`

### パフォーマンス改善
効率的フィルタリングにより、以下の改善を実現：

- **処理時間短縮**: 類似度順早期終了による不要処理の削減
- **メモリ使用量削減**: 中間結果保持の最小化
- **レスポンス向上**: top_k達成時の即座終了

### 保守性向上
コードの重複排除と責務分離により：

- **単一責任**: `is_post_text_match`による一貫した判定ロジック
- **再利用性**: テキストフィルタリング機能の汎用化
- **テスト容易性**: 機能の分離による単体テスト対応

## 技術的考察

### アーキテクチャ設計の妥当性
サーバー側でのクエリ再解釈アプローチの採用理由：

1. **後方互換性の保証**: 既存クライアントが無修正で動作
2. **開発効率**: クライアント側の同期的変更を回避
3. **機能集約**: 検索ロジックのサーバー側一元化
4. **将来拡張性**: 新しい検索構文の追加が容易

### 処理順序の最適化
V→T（ベクトル検索→テキスト絞り込み）処理順序の選択理由：

1. **実装簡便性**: 既存のベクトル検索結果をフィルタリング
2. **テンソル再利用**: 事前計算済みベクトルの活用
3. **結果一貫性**: 理論上T→Vと同一の結果を保証

### エラーハンドリング戦略
vector_searchでのベクトルクエリ必須要件：

- **API意図明確化**: vector_searchは純粋なベクトル検索API
- **責務分離**: テキスト専用はsearch_similarで適切に処理
- **エラー明確性**: 空ベクトルクエリ時の明確なエラーメッセージ

## 今後の展望

### 機能拡張の可能性
現在の基盤を活用した将来的な拡張：

1. **構文拡張**: AND/OR演算子の追加
2. **フィールド指定**: @user:alice のような特定フィールド検索
3. **正規表現**: regex:pattern のような高度なパターンマッチング
4. **類似度閾値**: score>0.8 のような類似度条件

### パフォーマンス最適化
さらなる効率化の検討課題：

1. **インデックス活用**: テキスト検索の高速化
2. **並列処理**: 大量データでの並列フィルタリング
3. **キャッシュ戦略**: 頻繁な検索パターンの結果キャッシュ

## 結論

V|T複合検索の導入により、検索機能の大幅な拡張を、既存システムの安定性を保ちながら実現した。特に、クライアント側の変更を一切必要としない透過的なアーキテクチャにより、保守性と拡張性を両立させた点が大きな成果である。

効率的なフィルタリングアルゴリズムの導入により、パフォーマンスも向上し、実用的な複合検索システムとして完成した。この基盤は今後のさらなる検索機能拡張への土台として活用できる。