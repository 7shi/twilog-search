#!/usr/bin/env python3
import asyncio
import safetensors.torch
import torch
from pathlib import Path
from typing import List, Set
from tqdm import tqdm
from embed_client import EmbedClient


async def load_tags_from_tsv(file_path: Path) -> Set[str]:
    """batch/tags.tsvからタグのsetを作成"""
    tags = set()
    
    with open(file_path, 'r', encoding='utf-8') as f:
        # 最初の1行（ヘッダー）を飛ばす
        next(f)
        
        for line in f:
            # post_idを除いてタグ部分を取得
            tag_columns = line.strip().split('\t')[1:]
            
            for tag in tag_columns:
                tag = tag.strip()
                if tag:  # 空でない場合のみ追加
                    tags.add(tag)
    
    return tags


async def vectorize_tags(tags: List[str], client: EmbedClient) -> List[torch.Tensor]:
    """タグリストをベクトル化"""
    vectors = []
    
    for tag in tqdm(tags, desc="ベクトル化中"):
        # embed_textでベクトル化（Ruri v3のprefix付き）
        result = await client.embed_text("トピック: " + tag)
        
        # decode_vectorでtensorを取得
        vector = client.decode_vector(result)
        vectors.append(vector)
    
    return vectors


async def save_vectors_and_tags(vectors: List[torch.Tensor], tags: List[str], 
                               vector_path: Path, tag_path: Path):
    """ベクトルとタグを保存"""
    # ベクトルをsafetensorsに保存
    stacked_vectors = torch.stack(vectors)
    tensors = {'vectors': stacked_vectors}
    safetensors.torch.save_file(tensors, vector_path)
    
    # タグをテキストファイルに保存
    with open(tag_path, 'w', encoding='utf-8') as f:
        for tag in tags:
            f.write(f"{tag}\n")


async def main():
    """メイン処理"""
    # パス設定
    batch_dir = Path('batch')
    tags_tsv_path = batch_dir / 'tags.tsv'
    tags_safetensors_path = batch_dir / 'tags.safetensors'
    tags_txt_path = batch_dir / 'tags.txt'
    
    # batch/tags.tsvからタグのsetを作成
    print("batch/tags.tsvからタグを読み込み中...")
    tags_set = await load_tags_from_tsv(tags_tsv_path)
    print(f"読み込み完了: {len(tags_set)}個のユニークなタグ")
    
    # タグをソートしてlistに変換
    sorted_tags = sorted(list(tags_set))
    print(f"ソート完了: {len(sorted_tags)}個のタグ")
    
    # EmbedClientを使用してベクトル化
    client = EmbedClient()
    print("タグのベクトル化を開始...")
    vectors = await vectorize_tags(sorted_tags, client)
    print("ベクトル化完了")
    
    # ベクトルとタグを保存
    print("ファイルに保存中...")
    await save_vectors_and_tags(vectors, sorted_tags, tags_safetensors_path, tags_txt_path)
    print(f"保存完了:")
    print(f"  - ベクトル: {tags_safetensors_path}")
    print(f"  - タグ: {tags_txt_path}")


if __name__ == "__main__":
    asyncio.run(main())