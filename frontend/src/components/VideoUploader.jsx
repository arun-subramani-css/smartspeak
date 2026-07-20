import React, { useState, useRef } from 'react';
import { UploadCloud, FileVideo, AlertCircle, CheckCircle, X, Loader2 } from 'lucide-react';

const MAX_SIZE_MB = 500;
const ALLOWED_EXTENSIONS = ['.mp4', '.avi', '.mov'];

export function VideoUploader({ onUploadSuccess }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  const validateFile = (file) => {
    if (!file) return 'No file selected.';

    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Invalid format '${ext}'. Only .mp4, .avi, and .mov files are supported.`;
    }

    const sizeMB = file.size / (1024 * 1024);
    if (sizeMB > MAX_SIZE_MB) {
      return `File size (${sizeMB.toFixed(1)}MB) exceeds maximum limit of ${MAX_SIZE_MB}MB.`;
    }

    return null;
  };

  const handleFileChange = (e) => {
    setErrorMessage('');
    const file = e.target.files[0];
    if (file) {
      const err = validateFile(file);
      if (err) {
        setErrorMessage(err);
        setSelectedFile(null);
      } else {
        setSelectedFile(file);
      }
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    setErrorMessage('');

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      const err = validateFile(file);
      if (err) {
        setErrorMessage(err);
        setSelectedFile(null);
      } else {
        setSelectedFile(file);
      }
    }
  };

  const handleUpload = () => {
    if (!selectedFile) return;

    const validationError = validateFile(selectedFile);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);
    setErrorMessage('');

    const formData = new FormData();
    formData.append('video', selectedFile);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/v1/upload', true);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100);
        setUploadProgress(percent);
      }
    };

    xhr.onload = () => {
      setIsUploading(false);
      if (xhr.status === 201 || xhr.status === 200) {
        try {
          const response = JSON.parse(xhr.responseText);
          if (onUploadSuccess) {
            onUploadSuccess(response.session_id);
          }
        } catch (e) {
          setErrorMessage('Upload succeeded but server response was invalid JSON.');
        }
      } else {
        try {
          const res = JSON.parse(xhr.responseText);
          setErrorMessage(res.detail || `Upload failed with status code ${xhr.status}`);
        } catch (e) {
          setErrorMessage(`Upload failed with status code ${xhr.status}: ${xhr.statusText}`);
        }
      }
    };

    xhr.onerror = () => {
      setIsUploading(false);
      setErrorMessage('Network error occurred during upload. Ensure backend server is running.');
    };

    xhr.send(formData);
  };

  const clearSelection = () => {
    setSelectedFile(null);
    setErrorMessage('');
    setUploadProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="glass-card" style={{ padding: '28px' }}>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '6px' }}>
          Upload Presentation Video
        </h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          Select an MP4, AVI, or MOV video file (up to 500MB). Audio and frames will be processed automatically.
        </p>
      </div>

      {/* Hidden File Input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept=".mp4,.avi,.mov"
        style={{ display: 'none' }}
      />

      {/* Dropzone */}
      {!selectedFile ? (
        <div
          className={`dropzone ${dragActive ? 'active' : ''}`}
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <UploadCloud size={48} color="var(--primary)" style={{ marginBottom: '12px' }} />
          <p style={{ fontWeight: 600, fontSize: '1.05rem', marginBottom: '6px' }}>
            Click to upload or drag & drop video
          </p>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Formats: .mp4, .avi, .mov • Max size: 500MB
          </p>
        </div>
      ) : (
        <div style={{
          background: 'rgba(15, 23, 42, 0.6)',
          border: '1px solid var(--border-color)',
          borderRadius: 'var(--radius-md)',
          padding: '20px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <div style={{
                background: 'rgba(99, 102, 241, 0.15)',
                padding: '12px',
                borderRadius: '10px',
                color: 'var(--primary)'
              }}>
                <FileVideo size={28} />
              </div>
              <div>
                <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)' }}>
                  {selectedFile.name}
                </h4>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • {selectedFile.type || 'video'}
                </p>
              </div>
            </div>
            {!isUploading && (
              <button
                onClick={clearSelection}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  padding: '4px'
                }}
              >
                <X size={20} />
              </button>
            )}
          </div>

          {/* Upload Progress Bar */}
          {isUploading && (
            <div style={{ marginTop: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '6px', color: 'var(--text-muted)' }}>
                <span>Uploading to server...</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="progress-bar-container">
                <div className="progress-bar-fill" style={{ width: `${uploadProgress}%` }} />
              </div>
            </div>
          )}

          {/* Upload Trigger Button */}
          {!isUploading && (
            <button
              className="gradient-button"
              onClick={handleUpload}
              style={{ width: '100%', padding: '14px', marginTop: '12px', fontSize: '1rem' }}
            >
              Start Upload & Process
            </button>
          )}
        </div>
      )}

      {/* Error Banner */}
      {errorMessage && (
        <div style={{
          marginTop: '16px',
          padding: '12px 16px',
          background: 'var(--danger-bg)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--danger)',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          fontSize: '0.9rem'
        }}>
          <AlertCircle size={20} style={{ flexShrink: 0 }} />
          <span>{errorMessage}</span>
        </div>
      )}
    </div>
  );
}
