import React, { useState, useRef, useCallback } from 'react';
import { X, Upload, RotateCw, ZoomIn, ZoomOut, Check, Image as ImageIcon } from 'lucide-react';
import ReactCrop from 'react-image-crop';
import type { Crop, PixelCrop } from 'react-image-crop';
import 'react-image-crop/dist/ReactCrop.css';

interface ImageCropModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCropComplete: (croppedImageBlob: Blob) => void;
  aspectRatio?: number;
  title?: string;
}

export const ImageCropModal: React.FC<ImageCropModalProps> = ({
  isOpen,
  onClose,
  onCropComplete,
  aspectRatio = 1, // Default to 1:1 (square)
  title = 'Crop Image',
}) => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [crop, setCrop] = useState<Crop>({
    unit: '%',
    width: 90,
    height: 90,
    x: 5,
    y: 5,
  });
  const [completedCrop, setCompletedCrop] = useState<PixelCrop | null>(null);
  const [scale, setScale] = useState(1);
  const [rotate, setRotate] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const onSelectFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const reader = new FileReader();
      reader.addEventListener('load', () => {
        setImageSrc(reader.result?.toString() || null);
      });
      reader.readAsDataURL(e.target.files[0]);
    }
  };

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      const file = files[0];
      if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.addEventListener('load', () => {
          setImageSrc(reader.result?.toString() || null);
        });
        reader.readAsDataURL(file);
      }
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const onImageLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    const { width, height } = e.currentTarget;
    const cropSize = Math.min(width, height) * 0.9;
    const x = (width - cropSize) / 2;
    const y = (height - cropSize) / 2;
    
    setCrop({
      unit: 'px',
      width: cropSize,
      height: cropSize,
      x,
      y,
    });
  }, []);

  const getCroppedImg = useCallback(async (): Promise<Blob | null> => {
    if (!completedCrop || !imgRef.current) {
      return null;
    }

    const image = imgRef.current;
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    if (!ctx) {
      return null;
    }

    const scaleX = image.naturalWidth / image.width;
    const scaleY = image.naturalHeight / image.height;

    // Set canvas size to the crop size
    canvas.width = completedCrop.width;
    canvas.height = completedCrop.height;

    // Apply transformations
    ctx.save();
    
    // Translate to center
    ctx.translate(canvas.width / 2, canvas.height / 2);
    
    // Apply rotation
    ctx.rotate((rotate * Math.PI) / 180);
    
    // Apply scale
    ctx.scale(scale, scale);
    
    // Draw image
    ctx.drawImage(
      image,
      completedCrop.x * scaleX,
      completedCrop.y * scaleY,
      completedCrop.width * scaleX,
      completedCrop.height * scaleY,
      -completedCrop.width / 2,
      -completedCrop.height / 2,
      completedCrop.width,
      completedCrop.height
    );

    ctx.restore();

    return new Promise((resolve) => {
      canvas.toBlob(
        (blob) => {
          resolve(blob);
        },
        'image/webp',
        0.95
      );
    });
  }, [completedCrop, scale, rotate]);

  const handleCropComplete = async () => {
    const croppedBlob = await getCroppedImg();
    if (croppedBlob) {
      onCropComplete(croppedBlob);
      handleClose();
    }
  };

  const handleClose = () => {
    setImageSrc(null);
    setCrop({ unit: '%', width: 90, height: 90, x: 5, y: 5 });
    setCompletedCrop(null);
    setScale(1);
    setRotate(0);
    setIsDragging(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="w-full max-w-3xl modal-panel rounded-[24px] shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 dark:border-zinc-700 bg-gradient-to-r from-emerald-500/5 to-cyan-500/5">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-500/10 rounded-xl">
              <ImageIcon className="w-5 h-5 text-emerald-600 dark:text-emerald-500" />
            </div>
            <h2 className="text-xl font-bold text-zinc-800 dark:text-zinc-200">{title}</h2>
          </div>
          <button
            onClick={handleClose}
            className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-zinc-600 dark:text-zinc-400" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {!imageSrc ? (
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              className={`relative flex flex-col items-center justify-center py-16 px-8 border-2 border-dashed rounded-2xl transition-all ${
                isDragging
                  ? 'border-emerald-500 bg-emerald-500/5 scale-[1.02]'
                  : 'border-zinc-300 dark:border-zinc-700 hover:border-emerald-400 dark:hover:border-emerald-600'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={onSelectFile}
                className="hidden"
              />
              
              <div className="flex flex-col items-center gap-4">
                <div className={`p-6 rounded-full transition-all ${
                  isDragging 
                    ? 'bg-emerald-500/20 scale-110' 
                    : 'bg-zinc-100 dark:bg-zinc-800'
                }`}>
                  <Upload className={`w-12 h-12 transition-colors ${
                    isDragging 
                      ? 'text-emerald-600 dark:text-emerald-500' 
                      : 'text-zinc-400'
                  }`} />
                </div>
                
                <div className="text-center space-y-2">
                  <p className="text-lg font-semibold text-zinc-700 dark:text-zinc-300">
                    {isDragging ? 'Drop image here' : 'Upload Avatar Image'}
                  </p>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    Drag and drop or{' '}
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="text-emerald-600 dark:text-emerald-500 font-semibold hover:underline"
                    >
                      browse files
                    </button>
                  </p>
                  <p className="text-xs text-zinc-400 dark:text-zinc-500">
                    Supports: JPG, PNG, GIF, WebP (Max 10MB)
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <>
              {/* Crop Area */}
              <div className="flex justify-center bg-zinc-100 dark:bg-zinc-800 rounded-xl p-4 min-h-[400px]">
                <ReactCrop
                  crop={crop}
                  onChange={(c) => setCrop(c)}
                  onComplete={(c) => setCompletedCrop(c)}
                  aspect={aspectRatio}
                  circularCrop={false}
                >
                  <img
                    ref={imgRef}
                    src={imageSrc}
                    alt="Crop preview"
                    style={{
                      transform: `scale(${scale}) rotate(${rotate}deg)`,
                      maxHeight: '400px',
                    }}
                    onLoad={onImageLoad}
                  />
                </ReactCrop>
              </div>

              {/* Controls */}
              <div className="space-y-4 p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-xl">
                {/* Zoom Control */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
                      Zoom
                    </span>
                    <span className="text-sm text-zinc-600 dark:text-zinc-400">
                      {Math.round(scale * 100)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <ZoomOut className="w-4 h-4 text-zinc-500 flex-shrink-0" />
                    <input
                      type="range"
                      min="0.5"
                      max="2"
                      step="0.1"
                      value={scale}
                      onChange={(e) => setScale(Number(e.target.value))}
                      className="flex-1 h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-emerald-500"
                    />
                    <ZoomIn className="w-4 h-4 text-zinc-500 flex-shrink-0" />
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex items-center justify-between gap-3">
                  <button
                    onClick={() => setRotate((prev) => (prev + 90) % 360)}
                    className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-zinc-700 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-600 transition-colors text-sm font-medium"
                  >
                    <RotateCw className="w-4 h-4" />
                    Rotate
                  </button>

                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="px-4 py-2 bg-white dark:bg-zinc-700 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-600 transition-colors text-sm font-medium"
                  >
                    Change Image
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        {imageSrc && (
          <div className="flex justify-end gap-3 px-6 py-4 border-t border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/50">
            <button
              onClick={handleClose}
              className="px-6 py-2.5 rounded-lg font-semibold text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleCropComplete}
              disabled={!completedCrop}
              className="flex items-center gap-2 px-6 py-2.5 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white rounded-lg font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-emerald-500/20"
            >
              <Check className="w-4 h-4" />
              Apply & Upload
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
