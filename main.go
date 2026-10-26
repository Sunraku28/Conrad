package main

import (
	"fmt"
	"image"
	"image/color"
	_ "image/png"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

var (
	baseStyle      = lipgloss.NewStyle().BorderStyle(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("240"))
	highlightStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("#00FFCC")).Bold(true)
	titleStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("#FF0055")).Bold(true).Padding(0, 1)
	subTitleStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("#FF9900")).Bold(true)
	dimStyle       = lipgloss.NewStyle().Foreground(lipgloss.Color("240"))

	logoASCII = `
   ____ ___  _   _ ____      _    ____
  / ___/ _ \| \ | |  _ \    / \  |  _ \
 | |  | | | |  \| | |_) |  / _ \ | | | |
 | |__| |_| | |\  |  _ <  / ___ \| |_| |
  \____\___/|_| \_|_| \_\/_/   \_\____/
`
)

type tool struct {
	name   string
	launch bool
}

type model struct {
	tools      []tool
	cursor     int
	width      int
	assetPath  string
	assetImage string
	selected   *tool
}

func initialModel() model {
	m := model{tools: []tool{
		{
			name:   "Conrad",
			launch: true,
		},
		{
			name: "Exit",
		},
	}}
	if root, err := repositoryRoot(); err == nil {
		m.assetPath = filepath.Join(root, "assets", "GodsHand.png")
	}
	return m
}

func (m model) Init() tea.Cmd { return nil }

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		if m.assetPath != "" {
			imageWidth, imageHeight := imageDimensions(m.width)
			m.assetImage, _ = renderImage(m.assetPath, imageWidth, imageHeight)
		}
	case tea.KeyMsg:
		switch msg.String() {
		case "ctrl+c", "q", "esc":
			return m, tea.Quit
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.tools)-1 {
				m.cursor++
			}
		case "enter", " ":
			m.selected = &m.tools[m.cursor]
			return m, tea.Quit
		}
	}
	return m, nil
}

func imageDimensions(terminalWidth int) (int, int) {
	if terminalWidth >= 122 {
		return 48, 16
	}
	return 36, 12
}

func (m model) View() string {
	if m.width == 0 {
		return "Initializing GodsHand-Conrad..."
	}
	if m.width < 52 {
		return "Terminal too small. Resize to at least 52 columns."
	}

	contentWidth := m.width - 2
	logo := titleStyle.Render(logoASCII)
	if m.assetImage != "" && m.width >= 96 {
		logo = lipgloss.JoinHorizontal(lipgloss.Center, m.assetImage, "  ", logo)
	}
	logoBox := baseStyle.Width(contentWidth).Align(lipgloss.Center).Render(logo)
	menuItems := ""
	for i, item := range m.tools {
		prefix, style := "  ", lipgloss.NewStyle()
		if m.cursor == i {
			prefix, style = "➤ ", highlightStyle
		}
		menuItems += style.Render(prefix+item.name) + "\n"
	}
	menuBox := baseStyle.Width(contentWidth).Height(9).Render(
		subTitleStyle.Render("GodsHand-Conrad") + "\n" +
			dimStyle.Render("Select Conrad to start the terminal agent.") + "\n\n" + menuItems,
	)

	return lipgloss.JoinVertical(lipgloss.Left, logoBox, menuBox)
}

// renderImage converts a PNG into ANSI true-color half blocks. Each terminal
// cell represents two vertical image pixels, keeping the image portable across
// terminals that support 24-bit color.
func renderImage(path string, width, height int) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()

	img, _, err := image.Decode(file)
	if err != nil {
		return "", err
	}
	bounds := img.Bounds()
	if bounds.Empty() || width < 1 || height < 1 {
		return "", fmt.Errorf("invalid image dimensions")
	}

	var output strings.Builder
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			top := blendOverTerminal(sampleImage(img, bounds, x, 2*y, width, 2*height))
			bottom := blendOverTerminal(sampleImage(img, bounds, x, 2*y+1, width, 2*height))
			switch {
			case top.A == 0 && bottom.A == 0:
				output.WriteByte(' ')
			case bottom.A == 0:
				fmt.Fprintf(&output, "\x1b[38;2;%d;%d;%dm▀", top.R, top.G, top.B)
			case top.A == 0:
				fmt.Fprintf(&output, "\x1b[38;2;%d;%d;%dm▄", bottom.R, bottom.G, bottom.B)
			default:
				fmt.Fprintf(&output, "\x1b[38;2;%d;%d;%dm\x1b[48;2;%d;%d;%dm▀", top.R, top.G, top.B, bottom.R, bottom.G, bottom.B)
			}
		}
		output.WriteString("\x1b[0m\n")
	}
	return strings.TrimSuffix(output.String(), "\n"), nil
}

// sampleImage averages every source pixel covered by an ANSI half-block. This
// avoids the jagged nearest-neighbour result from sampling one pixel per cell.
func sampleImage(img image.Image, bounds image.Rectangle, x, y, width, height int) color.NRGBA {
	startX := bounds.Min.X + x*bounds.Dx()/width
	endX := bounds.Min.X + (x+1)*bounds.Dx()/width
	startY := bounds.Min.Y + y*bounds.Dy()/height
	endY := bounds.Min.Y + (y+1)*bounds.Dy()/height

	var red, green, blue, alpha, pixels uint64
	for sourceY := startY; sourceY < endY; sourceY++ {
		for sourceX := startX; sourceX < endX; sourceX++ {
			pixel := color.NRGBAModel.Convert(img.At(sourceX, sourceY)).(color.NRGBA)
			red += uint64(pixel.R) * uint64(pixel.A)
			green += uint64(pixel.G) * uint64(pixel.A)
			blue += uint64(pixel.B) * uint64(pixel.A)
			alpha += uint64(pixel.A)
			pixels++
		}
	}
	if alpha == 0 || pixels == 0 {
		return color.NRGBA{}
	}
	return color.NRGBA{
		R: uint8(red / alpha),
		G: uint8(green / alpha),
		B: uint8(blue / alpha),
		A: uint8(alpha / pixels),
	}
}

// blendOverTerminal preserves fully transparent pixels and blends soft edges
// against the application's dark terminal background.
func blendOverTerminal(pixel color.NRGBA) color.NRGBA {
	if pixel.A == 0 {
		return pixel
	}
	const terminalBackground = 24
	if pixel.A == 255 {
		return pixel
	}
	alpha := uint16(pixel.A)
	return color.NRGBA{
		R: uint8((uint16(pixel.R)*alpha + terminalBackground*(255-alpha)) / 255),
		G: uint8((uint16(pixel.G)*alpha + terminalBackground*(255-alpha)) / 255),
		B: uint8((uint16(pixel.B)*alpha + terminalBackground*(255-alpha)) / 255),
		A: 255,
	}
}

func repositoryRoot() (string, error) {
	if root := os.Getenv("GODSHAND_CONRAD_ROOT"); root != "" {
		return filepath.Abs(root)
	}
	executable, err := os.Executable()
	if err == nil {
		root := filepath.Dir(executable)
		if _, statErr := os.Stat(filepath.Join(root, "GodsHand")); statErr == nil {
			return root, nil
		}
	}
	return os.Getwd()
}

func pythonExecutable(root string) string {
	if configured := os.Getenv("GODSHAND_CONRAD_PYTHON"); configured != "" {
		return configured
	}
	for _, candidate := range []string{filepath.Join(root, ".venv", "bin", "python"), filepath.Join(root, "venv", "bin", "python"), "python3", "python"} {
		if candidate == "python3" || candidate == "python" {
			return candidate
		}
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	return "python3"
}

func launchConrad() error {
	root, err := repositoryRoot()
	if err != nil {
		return err
	}
	if _, err := os.Stat(filepath.Join(root, "GodsHand", "src", "conrad.py")); err != nil {
		return fmt.Errorf("Conrad entry point is unavailable: %w", err)
	}

	cmd := exec.Command(pythonExecutable(root), "-m", "GodsHand.src.conrad")
	cmd.Dir = root
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	return cmd.Run()
}

func main() {
	program := tea.NewProgram(initialModel(), tea.WithAltScreen())
	result, err := program.Run()
	if err != nil {
		fmt.Fprintf(os.Stderr, "GodsHand-Conrad UI error: %v\n", err)
		os.Exit(1)
	}

	finalModel := result.(model)
	if finalModel.selected == nil || !finalModel.selected.launch {
		return
	}
	if err := launchConrad(); err != nil {
		fmt.Fprintf(os.Stderr, "Conrad exited with error: %v\n", err)
		if exitError, ok := err.(*exec.ExitError); ok {
			os.Exit(exitError.ExitCode())
		}
		if runtime.GOOS == "windows" {
			fmt.Fprintln(os.Stderr, "Set GODSHAND_CONRAD_PYTHON if Python is not on PATH.")
		}
		os.Exit(1)
	}
}
