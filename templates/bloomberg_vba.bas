' DAT Dashboard - Bloomberg Excel Automation
' Save this code in the workbook's ThisWorkbook module

Option Explicit

' Configuration
Private Const EXPORT_PATH As String = "C:\Users\matthewpotts\Documents\Claude\dat-dashboard\data\exports\bloomberg_data.csv"
Private Const DATA_SHEET As String = "Data"
Private Const WAIT_FOR_REFRESH As Integer = 60  ' seconds to wait for Bloomberg refresh

' ============================================
' AUTO-RUN ON WORKBOOK OPEN
' ============================================
Private Sub Workbook_Open()
    ' Uncomment the line below to enable auto-export on open
    ' Call ExportToCSV
End Sub

' ============================================
' MAIN EXPORT FUNCTION
' ============================================
Public Sub ExportToCSV()
    On Error GoTo ErrorHandler

    Dim ws As Worksheet
    Dim exportWb As Workbook
    Dim lastRow As Long
    Dim lastCol As Long
    Dim dataRange As Range
    Dim fso As Object
    Dim folderPath As String

    Application.ScreenUpdating = False
    Application.DisplayAlerts = False

    ' Step 1: Refresh Bloomberg data
    Call RefreshBloombergData

    ' Step 2: Wait for data to load
    Application.StatusBar = "Waiting for Bloomberg data to refresh..."
    Application.Wait Now + TimeValue("0:00:" & WAIT_FOR_REFRESH)

    ' Step 3: Get data range
    Set ws = ThisWorkbook.Sheets(DATA_SHEET)
    lastRow = ws.Cells(ws.Rows.Count, "A").End(xlUp).Row
    lastCol = ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column
    Set dataRange = ws.Range(ws.Cells(1, 1), ws.Cells(lastRow, lastCol))

    ' Step 4: Ensure export directory exists
    folderPath = Left(EXPORT_PATH, InStrRev(EXPORT_PATH, "\") - 1)
    Set fso = CreateObject("Scripting.FileSystemObject")
    If Not fso.FolderExists(folderPath) Then
        fso.CreateFolder folderPath
    End If

    ' Step 5: Copy data to new workbook and save as CSV
    dataRange.Copy
    Set exportWb = Workbooks.Add
    exportWb.Sheets(1).Range("A1").PasteSpecial xlPasteValues
    Application.CutCopyMode = False

    exportWb.SaveAs Filename:=EXPORT_PATH, FileFormat:=xlCSV
    exportWb.Close SaveChanges:=False

    ' Step 6: Log export
    Call LogExport

    Application.StatusBar = "Export completed: " & EXPORT_PATH
    Application.ScreenUpdating = True
    Application.DisplayAlerts = True

    MsgBox "Data exported successfully to:" & vbCrLf & EXPORT_PATH, vbInformation, "DAT Dashboard Export"
    Exit Sub

ErrorHandler:
    Application.ScreenUpdating = True
    Application.DisplayAlerts = True
    Application.StatusBar = False
    MsgBox "Export failed: " & Err.Description, vbCritical, "Export Error"
End Sub

' ============================================
' REFRESH BLOOMBERG DATA
' ============================================
Private Sub RefreshBloombergData()
    On Error Resume Next

    ' Method 1: Bloomberg Ribbon command
    Application.Run "RefreshAllStaticData"

    ' Method 2: If above fails, try Bloomberg API
    If Err.Number <> 0 Then
        Err.Clear
        Application.Run "BloombergUI.RefreshAllStaticData"
    End If

    ' Method 3: Force recalculation
    If Err.Number <> 0 Then
        Err.Clear
        Application.CalculateFull
    End If

    On Error GoTo 0
End Sub

' ============================================
' LOG EXPORT TIMESTAMP
' ============================================
Private Sub LogExport()
    On Error Resume Next

    Dim logSheet As Worksheet
    Dim nextRow As Long

    ' Check if Export_Log sheet exists
    Set logSheet = Nothing
    Set logSheet = ThisWorkbook.Sheets("Export_Log")

    If logSheet Is Nothing Then
        ' Create log sheet if it doesn't exist
        Set logSheet = ThisWorkbook.Sheets.Add(After:=ThisWorkbook.Sheets(ThisWorkbook.Sheets.Count))
        logSheet.Name = "Export_Log"
        logSheet.Range("A1").Value = "Export_Timestamp"
        logSheet.Range("B1").Value = "Status"
    End If

    ' Add log entry
    nextRow = logSheet.Cells(logSheet.Rows.Count, "A").End(xlUp).Row + 1
    logSheet.Cells(nextRow, 1).Value = Now
    logSheet.Cells(nextRow, 2).Value = "Success"

    On Error GoTo 0
End Sub

' ============================================
' MANUAL REFRESH (callable from button)
' ============================================
Public Sub ManualRefresh()
    Call RefreshBloombergData
    MsgBox "Bloomberg data refresh initiated. Please wait for data to update.", vbInformation
End Sub

' ============================================
' SCHEDULED EXPORT (for Task Scheduler)
' ============================================
Public Sub ScheduledExport()
    ' This sub is designed to be called from command line:
    ' "C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE" "path\to\workbook.xlsm" /e/ScheduledExport

    Call ExportToCSV

    ' Close workbook after export
    ThisWorkbook.Close SaveChanges:=True
End Sub
