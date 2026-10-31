package main

import (
	"context"
	"errors"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gongzhiqiang666-star/shuziren/server/internal/api"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/config"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/deepseek"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/media"
	"github.com/gongzhiqiang666-star/shuziren/server/internal/store"
)

func main() {
	if err := run(); err != nil {
		log.Print(err)
		os.Exit(1)
	}
}
func run() error {
	cfg, err := config.Load()
	if err != nil {
		return err
	}
	m, err := media.New(cfg.Media)
	if err != nil {
		return err
	}
	g, err := deepseek.New(cfg.DeepSeek)
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	initCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	st, err := store.Open(initCtx, cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer st.Close()
	if err = st.AcquireInstance(initCtx); err != nil {
		return err
	}
	if err = st.Migrate(initCtx); err != nil {
		return err
	}
	if err = st.Recover(initCtx); err != nil {
		return err
	}
	svc, err := api.New(st, m, g, cfg.AudioDir)
	if err != nil {
		return err
	}
	workerDone := make(chan struct{})
	go func() { defer close(workerDone); svc.RunWorker(ctx) }()
	lockFailure := make(chan struct{}, 1)
	go func() {
		t := time.NewTicker(2 * time.Second)
		defer t.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-t.C:
				c, cancel := context.WithTimeout(ctx, 2*time.Second)
				e := st.CheckInstance(c)
				cancel()
				if e != nil {
					select {
					case lockFailure <- struct{}{}:
					default:
					}
					stop()
					return
				}
			}
		}
	}()
	server := &http.Server{Addr: cfg.Addr, Handler: api.Router(svc, cfg.Token, cfg.WebDist), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, WriteTimeout: 130 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 16 << 10, BaseContext: func(net.Listener) context.Context { return ctx }}
	serveErr := make(chan error, 1)
	go func() { serveErr <- server.ListenAndServe() }()
	log.Printf("shuziren local workbench %s listening on %s", api.Version, cfg.Addr)
	var result error
	select {
	case <-ctx.Done():
	case err = <-serveErr:
		if !errors.Is(err, http.ErrServerClosed) {
			result = errors.New("HTTP listener failed; check APP_ADDR and port availability")
		}
		stop()
	}
	shutdown, cancelShutdown := context.WithTimeout(context.Background(), 35*time.Second)
	defer cancelShutdown()
	if err = server.Shutdown(shutdown); err != nil {
		_ = server.Close()
	}
	select {
	case <-workerDone:
	case <-time.After(10 * time.Second):
		result = errors.New("worker did not stop within shutdown timeout")
	}
	select {
	case <-lockFailure:
		return errors.New("database instance lock connection was lost; backend stopped to prevent duplicate queue execution")
	default:
	}
	return result
}
