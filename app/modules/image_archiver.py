"""
Image Archiver Module
Handles downloading and local storage of item snapshot images
"""
import os
import hashlib
from pathlib import Path
from typing import Optional
import httpx
from PIL import Image
import io


class ImageArchiver:
    """Downloads and manages local snapshot images"""
    
    def __init__(self, snapshots_dir: str = "/app/data/snapshots"):
        self.snapshots_dir = Path(snapshots_dir)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        
        # HTTP client with timeout and retry settings
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
    
    async def download_and_save(
        self, 
        image_url: str, 
        order_id: str,
        force_redownload: bool = False
    ) -> Optional[str]:
        """
        Download image from URL and save locally
        Returns the local file path if successful, None otherwise
        """
        if not image_url:
            return None
        
        # Generate filename based on order_id
        file_extension = self._get_extension_from_url(image_url)
        local_filename = f"{order_id}{file_extension}"
        local_path = self.snapshots_dir / local_filename
        
        # Skip if already exists and not forcing redownload
        if local_path.exists() and not force_redownload:
            return str(local_path)
        
        try:
            # Download image
            response = await self.client.get(image_url)
            response.raise_for_status()
            
            # Validate it's actually an image
            image_data = response.content
            try:
                img = Image.open(io.BytesIO(image_data))
                img.verify()  # Verify it's a valid image
            except Exception as e:
                print(f"Invalid image data for {order_id}: {e}")
                return None
            
            # Save to local path
            with open(local_path, 'wb') as f:
                f.write(image_data)
            
            # Optimize/compress if it's too large
            await self._optimize_image(local_path)
            
            return str(local_path)
            
        except httpx.HTTPError as e:
            print(f"HTTP error downloading image for {order_id}: {e}")
            return None
        except Exception as e:
            print(f"Error downloading image for {order_id}: {e}")
            return None
    
    async def _optimize_image(self, image_path: Path, max_size_kb: int = 500):
        """
        Optimize image size if it's too large
        Converts to JPEG and compresses if needed
        """
        try:
            file_size_kb = image_path.stat().st_size / 1024
            
            if file_size_kb > max_size_kb:
                img = Image.open(image_path)
                
                # Convert to RGB if necessary (for PNG with transparency)
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # Save with compression
                output_path = image_path.with_suffix('.jpg')
                img.save(output_path, 'JPEG', quality=85, optimize=True)
                
                # Remove original if different format
                if output_path != image_path:
                    image_path.unlink()
                
        except Exception as e:
            print(f"Error optimizing image {image_path}: {e}")
    
    def _get_extension_from_url(self, url: str) -> str:
        """Extract file extension from URL, default to .jpg"""
        url_lower = url.lower()
        
        if '.png' in url_lower:
            return '.png'
        elif '.gif' in url_lower:
            return '.gif'
        elif '.webp' in url_lower:
            return '.webp'
        elif '.bmp' in url_lower:
            return '.bmp'
        else:
            return '.jpg'
    
    async def get_local_path(self, order_id: str) -> Optional[str]:
        """
        Get local path for an order's snapshot if it exists
        Checks multiple possible extensions
        """
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            local_path = self.snapshots_dir / f"{order_id}{ext}"
            if local_path.exists():
                return str(local_path)
        
        return None
    
    async def delete_snapshot(self, order_id: str) -> bool:
        """Delete snapshot for a given order_id"""
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            local_path = self.snapshots_dir / f"{order_id}{ext}"
            if local_path.exists():
                try:
                    local_path.unlink()
                    return True
                except Exception as e:
                    print(f"Error deleting snapshot {local_path}: {e}")
                    return False
        
        return False
    
    async def cleanup_orphaned_snapshots(self, valid_order_ids: set) -> int:
        """
        Remove snapshots that don't correspond to any order in the database
        Returns count of deleted files
        """
        deleted_count = 0
        
        for snapshot_file in self.snapshots_dir.glob("*"):
            if snapshot_file.is_file():
                # Extract order_id from filename (remove extension)
                order_id = snapshot_file.stem
                
                if order_id not in valid_order_ids:
                    try:
                        snapshot_file.unlink()
                        deleted_count += 1
                    except Exception as e:
                        print(f"Error deleting orphaned snapshot {snapshot_file}: {e}")
        
        return deleted_count
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
