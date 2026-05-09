let canvas = document.getElementById('signatureCanvas');
let ctx = canvas.getContext('2d');
let isDrawing = false;
let lastX = 0;
let lastY = 0;

// Set canvas background
ctx.fillStyle = '#ffffff';
ctx.fillRect(0, 0, canvas.width, canvas.height);

// Drawing functions
canvas.addEventListener('mousedown', startDrawing);
canvas.addEventListener('mousemove', draw);
canvas.addEventListener('mouseup', stopDrawing);
canvas.addEventListener('mouseout', stopDrawing);

// Touch support
canvas.addEventListener('touchstart', handleTouch);
canvas.addEventListener('touchmove', handleTouch);
canvas.addEventListener('touchend', stopDrawing);

function startDrawing(e) {
  isDrawing = true;
  const rect = canvas.getBoundingClientRect();
  lastX = e.clientX - rect.left;
  lastY = e.clientY - rect.top;
}

function draw(e) {
  if (!isDrawing) return;
  
  const rect = canvas.getBoundingClientRect();
  const currentX = e.clientX - rect.left;
  const currentY = e.clientY - rect.top;
  
  ctx.strokeStyle = '#000000';
  ctx.lineWidth = 2;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(lastX, lastY);
  ctx.lineTo(currentX, currentY);
  ctx.stroke();
  
  lastX = currentX;
  lastY = currentY;
}

function stopDrawing() {
  isDrawing = false;
  updateSignatureData();
}

function handleTouch(e) {
  e.preventDefault();
  const touch = e.touches[0];
  const mouseEvent = new MouseEvent(e.type === 'touchstart' ? 'mousedown' : 
                                    e.type === 'touchmove' ? 'mousemove' : 'mouseup', {
    clientX: touch.clientX,
    clientY: touch.clientY
  });
  canvas.dispatchEvent(mouseEvent);
}

function clearSignature() {
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  document.getElementById('signatureData').value = '';
  document.getElementById('typedSignature').value = '';
}

function updateSignatureData() {
  const dataURL = canvas.toDataURL('image/png');
  document.getElementById('signatureData').value = dataURL;
}

// Handle typed signature
document.getElementById('typedSignature').addEventListener('input', function() {
  const typedName = this.value.trim();
  if (typedName) {
    // Clear canvas and use typed name
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#000000';
    ctx.font = '24px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(typedName, canvas.width / 2, canvas.height / 2);
    updateSignatureData();
  }
});

// Form submission
document.getElementById('signatureForm').addEventListener('submit', function(e) {
  const signatureData = document.getElementById('signatureData').value;
  const typedSignature = document.getElementById('typedSignature').value.trim();
  
  if (!signatureData && !typedSignature) {
    e.preventDefault();
    alert('Please provide a signature (draw or type your name)');
    return false;
  }
  
  // If only typed signature, use that
  if (!signatureData && typedSignature) {
    document.getElementById('signatureData').value = typedSignature;
  }
  
  // Disable submit button
  document.getElementById('submitBtn').disabled = true;
  document.getElementById('submitBtn').innerHTML = '<i class="bi bi-hourglass-split me-1"></i>Processing...';
});
