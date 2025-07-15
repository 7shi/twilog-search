#!/usr/bin/env python3
"""
processed_contentテーブルのテキストをRuri3でベクトル化し、分割safetensorsファイルに保存するスクリプト
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

MODEL = "cl-nagoya/ruri-v3-310m"

# モデルキャッシュ（グローバル辞書）
_model_cache = {}

def get_model(device="cpu"):
    """
    モデルを取得する（キャッシュ機能付き）
    
    Args:
        device: 使用するデバイス
        
    Returns:
        SentenceTransformerモデル
    """
    cache_key = f"{MODEL}_{device}"
    
    if cache_key not in _model_cache:
        print("sentence_transformersをインポート中...")
        from sentence_transformers import SentenceTransformer
        print(f"Ruri v3モデルを読み込み中... (device: {device})")
        _model_cache[cache_key] = SentenceTransformer(MODEL, device=device)
    
    return _model_cache[cache_key]

def embed_text(model, text):
    """
    テキストをベクトル化する
    
    Args:
        model: SentenceTransformerモデル
        text: ベクトル化対象のテキスト
        
    Returns:
        正規化されたベクトル
    """
    return model.encode([f"検索文書: {text}"], normalize_embeddings=True, convert_to_tensor=True)[0]

def load_data_from_csv(csv_path):
    """
    CSVファイルからデータを読み込む
    
    Args:
        csv_path: CSVファイルのパス
        
    Returns:
        (post_id, content)のリスト
    """
    # data_csvを遅延読み込み
    from data_csv import TwilogDataAccess, strip_content
    
    data_access = TwilogDataAccess(csv_path)
    
    # 全投稿データを取得
    data = []
    for post_id, post_data in tqdm(data_access.posts_data.items(), desc="データ確認"):
        content = strip_content(post_data['content'])
        if content:  # 空でない場合のみ追加
            data.append((post_id, content))
    return data

def save_chunk(chunk_data, chunk_id, output_dir, model):
    """
    チャンクデータをsafetensorsファイルに保存する
    
    Args:
        chunk_data: (post_id, processed_content)のリスト
        chunk_id: チャンクID
        output_dir: 出力ディレクトリ
        model: SentenceTransformerモデル
    """
    if not chunk_data:
        return
    
    # ベクトル化
    post_ids = []
    vectors = []
    
    import torch
    for post_id, content in tqdm(chunk_data, desc=f"Chunk {chunk_id:04d}"):
        post_ids.append(post_id)
        vector = embed_text(model, content)
        vectors.append(vector)
    
    # テンソルに変換
    post_ids_tensor = torch.tensor(post_ids, dtype=torch.int64)
    vectors_tensor = torch.stack(vectors)
    
    # safetensorsファイルに保存
    import safetensors.torch
    filename = output_dir / f"{chunk_id:04d}.safetensors"
    safetensors.torch.save_file({
        "post_ids": post_ids_tensor,
        "vectors": vectors_tensor
    }, filename)

def create_metadata(total_posts, chunk_size, output_dir, embedding_dim, source_path, source_type="csv"):
    """
    メタデータファイルを作成する
    
    Args:
        total_posts: 総投稿数
        chunk_size: チャンクサイズ
        output_dir: 出力ディレクトリ
        embedding_dim: 埋め込み次元数
        source_path: ソースファイルのパス
        source_type: ソースファイルのタイプ（csv, jsonl等）
    """
    chunks = (total_posts + chunk_size - 1) // chunk_size
    
    # ソースファイルのパスをoutput_dirの親ディレクトリからの相対パスに変換
    source_relative_path = os.path.relpath(source_path, output_dir.parent)
    
    metadata = {
        "total_posts": total_posts,
        "chunk_size": chunk_size,
        "chunks": chunks,
        "model": MODEL,
        "embedding_dim": embedding_dim,
        "source_path": source_relative_path,
        "source_type": source_type
    }
    
    with open(output_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

def find_next_available_chunk_id(output_dir):
    """
    次に利用可能なチャンクIDを見つける
    
    Args:
        output_dir: 出力ディレクトリ
        
    Returns:
        利用可能なチャンクID
    """
    if not output_dir.exists():
        return 0
    
    # 0から順番に空いている番号を探す
    chunk_id = 0
    while (output_dir / f"{chunk_id:04d}.safetensors").exists():
        chunk_id += 1
    
    return chunk_id

def vectorize_data(data, output_dir, source_path, source_type="csv", chunk_size=1000, device="cpu", resume=True):
    """
    データをベクトル化してsafetensorsファイルに保存する汎用関数
    
    Args:
        data: (post_id, content)のリスト
        output_dir: 出力ディレクトリのパス
        source_path: ソースファイルのパス（メタデータ用）
        source_type: ソースファイルのタイプ（csv, jsonl等）
        chunk_size: チャンクサイズ
        device: 使用するデバイス
        resume: 中断・再開機能を使用するか
    """
    # 必要なライブラリを遅延読み込み
    import safetensors.torch
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    total_posts = len(data)
    all_post_ids = set(post_id for post_id, _ in data)
    print(f"総投稿数: {total_posts}")
    
    # 既存のsafetensorsファイルからpost_idを収集
    processed_post_ids = set()
    if output_path.exists():
        files = sorted(output_path.glob("*.safetensors"))
        for safetensors_file in tqdm(files, desc="既存確認"):
            try:
                tensors = safetensors.torch.load_file(safetensors_file)
                if "post_ids" in tensors:
                    file_post_ids = tensors["post_ids"].tolist()
                    # 重複チェック
                    duplicates = processed_post_ids.intersection(file_post_ids)
                    if duplicates:
                        print(f"\nエラー: post_idに重複があります: {duplicates}")
                        print(f"ファイル: {safetensors_file}")
                        return
                    processed_post_ids.update(file_post_ids)
            except Exception as e:
                print(f"警告: {safetensors_file}の読み込みに失敗: {e}")
    
    # 変換済み・残りpost_id数を表示
    remaining_post_ids = all_post_ids - processed_post_ids
    print(f"変換済み: {len(processed_post_ids)}件")
    print(f"残り: {len(remaining_post_ids)}件")
    
    # 全件完了していれば終了
    if not remaining_post_ids:
        print("すべてのpost_idが変換済みです")
        return
    
    # 変換が必要な場合のみモデルを取得
    model = get_model(device)
    
    # テストベクトルで次元数を確認
    test_vector = embed_text(model, "test")
    embedding_dim = len(test_vector)
    print(f"埋め込み次元数: {embedding_dim}")
    
    # 残りのpost_idのみを対象に変換
    remaining_data = [(post_id, content) for post_id, content in data if post_id in remaining_post_ids]
    
    # チャンクサイズずつ処理
    chunk_count = (len(remaining_data) + chunk_size - 1) // chunk_size
    for i in range(chunk_count):
        chunk_data = remaining_data[i * chunk_size : (i + 1) * chunk_size]
        chunk_id = find_next_available_chunk_id(output_path)
        print(f"チャンク ID: {chunk_id:04d} ({i+1}/{chunk_count}): {len(chunk_data)}件")
        save_chunk(chunk_data, chunk_id, output_path, model)
    
    # メタデータ作成
    create_metadata(total_posts, chunk_size, output_path, embedding_dim, source_path, source_type)
    print(f"出力先: {output_dir}")

def vectorize_csv(csv_path, output_dir, chunk_size=1000, device="cpu", resume=True):
    """
    CSVファイルをベクトル化してsafetensorsファイルに保存する
    
    Args:
        csv_path: CSVファイルのパス
        output_dir: 出力ディレクトリのパス
        chunk_size: チャンクサイズ
        device: 使用するデバイス
        resume: 中断・再開機能を使用するか
    """
    # データ読み込み
    data = load_data_from_csv(csv_path)
    
    # 汎用関数を呼び出し
    vectorize_data(data, output_dir, csv_path, "csv", chunk_size, device, resume)

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="CSVファイルをベクトル化してsafetensorsファイルに保存"
    )
    
    parser.add_argument("csv_file", help="CSVファイルのパス")
    parser.add_argument("--output-dir", default="embeddings", help="出力ディレクトリ（デフォルト: embeddings）")
    parser.add_argument("--chunk-size", type=int, default=1000, help="チャンクサイズ（デフォルト: 1000）")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu", help="使用するデバイス")
    parser.add_argument("--no-resume", action="store_true", help="中断・再開機能を無効にする")
    
    args = parser.parse_args()
    
    start_time = datetime.now()
    print("ベクトル化開始:", start_time)
    
    vectorize_csv(
        args.csv_file,
        args.output_dir,
        args.chunk_size,
        args.device,
        not args.no_resume
    )
    
    end_time = datetime.now()
    elapsed = end_time - start_time
    print("ベクトル化完了:", end_time)
    print(f"所要時間: {elapsed} ({elapsed.total_seconds():.2f}秒)")

if __name__ == "__main__":
    main()
