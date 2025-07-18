#!/usr/bin/env python3
import asyncio
import safetensors.torch
import torch
from pathlib import Path
from typing import List
from tqdm import tqdm
from embed_client import EmbedClient


async def main():
    """batch/tags.txtからタグを読み込み、ベクトル化してsafetensorsに出力"""
    # パス設定
    batch_dir = Path('batch')
    tags_txt_path = batch_dir / 'tags.txt'
    tags_safetensors_path = batch_dir / 'tags.safetensors'
    
    if not tags_txt_path.exists():
        print(f"エラー: {tags_txt_path} が見つかりません")
        return
    
    # tags.txtからタグを読み込み
    print(f"タグを読み込み中: {tags_txt_path}")
    tags = []
    with open(tags_txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            tag = line.strip()
            if tag:
                tags.append(tag)
    
    print(f"読み込み完了: {len(tags)}個のタグ")
    
    # EmbedClientを使用してベクトル化
    client = EmbedClient()
    print("タグのベクトル化を開始...")
    
    vectors = []
    for tag in tqdm(tags, desc="ベクトル化中"):
        # embed_textでベクトル化（Ruri v3のprefix付き）
        result = await client.embed_text("トピック: " + tag)
        
        # decode_vectorでtensorを取得
        vector = client.decode_vector(result)
        vectors.append(vector)
    
    print("ベクトル化完了")
    
    # ベクトルをsafetensorsに保存
    print(f"ベクトルを保存中: {tags_safetensors_path}")
    stacked_vectors = torch.stack(vectors)
    tensors = {'vectors': stacked_vectors}
    safetensors.torch.save_file(tensors, tags_safetensors_path)
    
    print(f"完了: {len(tags)}個のタグベクトルを保存しました")
    print(f"ファイル: {tags_safetensors_path}")


if __name__ == "__main__":
    asyncio.run(main())