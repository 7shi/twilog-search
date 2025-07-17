# ベクトルストア

## なぜこの実装が存在するか

### SearchEngineのベクトル管理問題
**Problem**: SearchEngineの`_load_all_vectors()`メソッドでreasoning/summaryベクトルのpost_idsを破棄してcontentのpost_idsを流用していたため、post_idとベクトルの対応関係が破綻し、検索精度が大幅に低下していた。

**Solution**: post_idをキーとして独立したベクトル管理を行うVectorStoreクラスを作成し、正確な対応関係を保証する方針を採用。

### 遅延読み込みによるメモリ効率化
**Problem**: 大量のベクトルデータを常にメモリに保持するとメモリ使用量が膨大になり、不要な読み込み時間が発生していた。

**Solution**: コンストラクタではメタデータのみ読み込み、実際のベクトル読み込みは`load_vectors()`を呼び出した時点で行う遅延読み込みを採用。

### 独立したベクトル検索機能
**Problem**: SearchEngineは複雑な検索機能と統合されており、純粋なベクトル類似度検索が困難で、デバッグや検証が複雑になっていた。

**Solution**: ベクトル検索機能を独立したクラスとして分離し、シンプルで再利用可能な設計を採用。

### 高速なpost_id検索
**Problem**: 大量のpost_idリストから線形検索を行うと、特定のpost_idのベクトルを取得する際に時間がかかっていた。

**Solution**: post_id→indexのマッピング辞書を構築し、O(1)での高速アクセスを実現。

### post_idソートによるハイブリッド検索最適化
**Problem**: SearchEngineでハイブリッド検索を行う際、各VectorStoreのpost_idの順序が異なるため、共通post_idに対するベクトルの対応関係が複雑になっていた。また、torch.catとtorch.argsortによるソート処理で、post_idのfloat変換により精度が失われる問題が発生していた。

**Solution**: load_vectors()で各チャンクのpost_idとベクトルをタプルリストに格納し、Pythonの通常ソートアルゴリズムを使用してpost_id順にソート。post_idの整数精度を保持しつつ、ベクトルとの対応関係を正確に管理。これにより、SearchEngineでのマスク処理が簡素化され、ハイブリッド検索の効率が大幅に向上した。

### 相対パス解決の統一化
**Problem**: vector_dirの親ディレクトリからの相対パスでファイルを参照する場合、各利用箇所で`vector_dir.parent / relative_path`の処理を重複実装する必要があり、コードの保守性が低下していた。

**Solution**: `get_relative_path()`メソッドを追加し、相対パス解決を一元化。vector_dirの親ディレクトリからの相対パスを受け取り、絶対パスのPathオブジェクトを返す統一的なインターフェースを提供。これにより、メタデータに記録された相対パスを簡潔に解決でき、コードの一貫性と保守性が向上した。