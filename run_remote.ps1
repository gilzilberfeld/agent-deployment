# Replace the remote-server-address with the Agent URL
Invoke-RestMethod -Uri "http://remote-server-address/diff" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"file1":"file1.json", "file2":"file2.json"}' `
  | Select-Object -ExpandProperty diff `
  | ConvertTo-Json -Depth 10